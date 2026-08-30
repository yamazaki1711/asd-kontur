"""Durable assistant worker using bounded Gateway context and loopback Qwen."""

# ruff: noqa: E501, RUF001 -- Russian professional copy is intentional.

from __future__ import annotations

import json
import signal
import time
import urllib.error
import urllib.request
from http.client import IncompleteRead, RemoteDisconnected
from typing import Any
from uuid import uuid4

from asd_kontur.application_spine.models import semantic_digest
from asd_kontur.knowledge.gateway import (
    ASSISTANT_CONTRACT_VERSION,
    ASSISTANT_SCHEMA_ID,
    GatewayContext,
    GatewayRequest,
    KnowledgeGateway,
)

from .gateway import ASSISTANT_TOOL, ProfessionalAssistantKnowledgeQuery
from .models import ClaimedTurn
from .postgres import AssistantRepository

MODE_INSTRUCTIONS = {
    "Tender": "Оценивайте договорные риски, расхождения ПД/РД, ВОР и сметы для подрядчика.",
    "Support": "Помогайте с контролем работ, материалами, АОСР и комплектом исполнительной документации.",
    "Audit": "Выделяйте несоответствия, пробелы, последствия и порядок устранения замечаний.",
    "Restoration": "Разделяйте восстановимые проекты документов и сведения, которые нельзя фабриковать.",
}


class _Audit:
    def record(self, **_: Any) -> None:
        return


class _GenerationCancelled(Exception):
    """The user stopped a turn after its durable cancellation request."""


class _QwenStreamInterrupted(Exception):
    """The loopback inference stream ended without a terminal response."""


class AssistantWorker:
    def __init__(
        self,
        repository: AssistantRepository,
        knowledge: ProfessionalAssistantKnowledgeQuery,
        *,
        identity: str,
        qwen_url: str = "http://127.0.0.1:8790/generate",
        lease_seconds: int = 900,
    ) -> None:
        self._repository = repository
        self._knowledge = knowledge
        self._gateway = KnowledgeGateway(knowledge, _Audit())
        self._identity = identity
        self._qwen_url = qwen_url
        self._lease_seconds = lease_seconds
        self._stopping = False

    def run_forever(self) -> None:
        signal.signal(signal.SIGTERM, lambda *_: self._request_stop())
        signal.signal(signal.SIGINT, lambda *_: self._request_stop())
        while not self._stopping:
            claimed = self._repository.claim(self._identity, self._lease_seconds)
            if claimed is None:
                time.sleep(0.3)
                continue
            self._run(claimed)

    def _request_stop(self) -> None:
        self._stopping = True

    def _run(self, claimed: ClaimedTurn) -> None:
        self._repository.start(claimed)
        try:
            response = self._gateway.invoke(
                GatewayRequest(
                    ASSISTANT_TOOL,
                    ASSISTANT_CONTRACT_VERSION,
                    ASSISTANT_SCHEMA_ID,
                    ASSISTANT_CONTRACT_VERSION,
                    {"query": claimed.question, "mode": claimed.mode.value},
                ),
                GatewayContext(
                    claimed.requested_by_identity_id,
                    f"{ASSISTANT_TOOL}.invoke",
                    "professional_assistant",
                    uuid4(),
                    claimed.organization_id,
                    claimed.workspace_id,
                ),
            )
            prompt = _build_prompt(
                claimed,
                response.result,
                self._repository.history_for_prompt(claimed),
            )
            context_digest = semantic_digest(response.result)
            try:
                content = self._generate(claimed, prompt)
            except (_GenerationCancelled, urllib.error.HTTPError):
                raise
            except Exception as exc:
                raise _QwenStreamInterrupted from exc
            if self._repository.heartbeat(claimed, self._lease_seconds):
                raise _GenerationCancelled
            if not content.strip():
                raise RuntimeError("qwen_empty_response")
            sources = tuple(dict(item) for item in response.result.get("sources", []))
            actions = _action_proposals(claimed)
            self._repository.complete(
                claimed,
                content=content.strip(),
                context_digest=context_digest,
                sources=sources,
                action_proposals=actions,
            )
        except _GenerationCancelled:
            self._repository.fail(claimed, "assistant_cancelled")
        except urllib.error.HTTPError as error:
            code = "qwen_runtime_busy" if error.code == 429 else "qwen_runtime_unavailable"
            self._repository.fail(claimed, code, reconciliation=error.code >= 500)
        except _QwenStreamInterrupted:
            self._repository.fail(claimed, "qwen_stream_interrupted", reconciliation=True)
        except (
            urllib.error.URLError,
            TimeoutError,
            ConnectionError,
            OSError,
            IncompleteRead,
            RemoteDisconnected,
            json.JSONDecodeError,
        ):
            self._repository.fail(claimed, "qwen_stream_interrupted", reconciliation=True)
        except Exception:
            self._repository.fail(claimed, "assistant_generation_failed")

    def _generate(self, claimed: ClaimedTurn, prompt: str) -> str:
        request = urllib.request.Request(
            self._qwen_url,
            data=json.dumps({"prompt": prompt, "max_tokens": 440}, ensure_ascii=False).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        chunks: list[str] = []
        buffered = ""
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(request, timeout=900) as response:
            while line := response.readline():
                event = json.loads(line)
                if event.get("event") != "delta":
                    continue
                text = str(event.get("text", ""))
                chunks.append(text)
                buffered += text
                if len(buffered) >= 24 or "\n" in buffered:
                    self._repository.append_delta(claimed, buffered)
                    buffered = ""
                    if self._repository.heartbeat(claimed, self._lease_seconds):
                        raise _GenerationCancelled
                if self._stopping:
                    raise ConnectionError("assistant_worker_stopping")
        if buffered:
            self._repository.append_delta(claimed, buffered)
        return "".join(chunks)


def _build_prompt(
    claimed: ClaimedTurn,
    context: dict[str, Any],
    history: tuple[dict[str, str], ...],
) -> str:
    model_context = {key: value for key, value in context.items() if key != "sources"}
    return f"""Вы — инженерный помощник программного комплекса АСД-КОНТУР.
Отвечайте только по предоставленному ниже ограниченному контексту Knowledge Gateway.
Не придумывайте факты, документы, подписи, даты, измерения, геометрию или результаты испытаний.
Методическое пособие — рекомендация, НТД — нормативный источник, сведения объекта — факты только
в указанном состоянии. Актуальность редакций НТД не проверялась: не утверждайте обратное.
Если данных недостаточно, прямо перечислите, чего не хватает.
Не показывайте внутренние коды, JSON, ход рассуждения или технические идентификаторы.
{MODE_INSTRUCTIONS[claimed.mode.value]}

Сформируйте краткий ответ на русском языке. В каждом разделе не более трёх пунктов:
### Краткий ответ
### Практическое пояснение
### Применительно к текущему объекту
### Что требуется сделать
### Ограничения и недостающие сведения
Ссылки на источники интерфейс добавит отдельно; не выдумывайте номера источников.

История текущего диалога:
{json.dumps(history, ensure_ascii=False, default=str)}

Контекст Knowledge Gateway:
{json.dumps(model_context, ensure_ascii=False, default=str)}

Вопрос пользователя: {claimed.question}
"""


def _action_proposals(claimed: ClaimedTurn) -> tuple[dict[str, Any], ...]:
    route = {
        "Tender": "result",
        "Support": "support-id",
        "Audit": "result",
        "Restoration": "result",
    }[claimed.mode.value]
    return (
        {
            "kind": "open_workspace_result",
            "label": "Открыть рабочий результат",
            "href": f"/modes/{claimed.mode.value.lower()}/workspaces/{claimed.workspace_id}/{route}",
            "requires_confirmation": False,
        },
    )


if __name__ == "__main__":
    raise SystemExit("Use asd_kontur.application_spine.runtime run-assistant-worker")
