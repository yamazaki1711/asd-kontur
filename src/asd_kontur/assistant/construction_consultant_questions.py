"""Synchronous, evidence-bound question service for the platform consultant."""

# ruff: noqa: RUF001 -- Russian professional prompt is intentional.

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from http.client import IncompleteRead, RemoteDisconnected
from typing import Any, Protocol
from uuid import UUID

from asd_kontur.assistant.construction_consultant_postgres import (
    ConstructionConsultantMessage,
)
from asd_kontur.assistant.profiles import (
    CONSTRUCTION_CONSULTANT_MODEL_PROFILE,
    CONSTRUCTION_CONSULTANT_PROFILE,
)
from asd_kontur.knowledge.gateway import GatewayResponse


class ConstructionConsultantQuestionError(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class ConstructionConsultantModel(Protocol):
    def complete(self, prompt: str) -> str: ...


class ConstructionConsultantHistory(Protocol):
    def organization_id(self, owner_identity_id: str) -> UUID: ...

    def messages(
        self, owner_identity_id: str, conversation_id: UUID
    ) -> tuple[ConstructionConsultantMessage, ...]: ...


class ConstructionConsultantMessageStore(Protocol):
    def messages_for_request(
        self,
        organization_id: UUID,
        conversation_id: UUID,
        owner_identity_id: str,
        request_id: UUID,
    ) -> tuple[ConstructionConsultantMessage, ...]: ...

    def append_message(
        self,
        organization_id: UUID,
        conversation_id: UUID,
        owner_identity_id: str,
        role: str,
        content: str,
        *,
        sources: tuple[dict[str, Any], ...] = (),
        model_identity: str | None = None,
        model_profile_version: str | None = None,
        request_id: UUID | None = None,
    ) -> ConstructionConsultantMessage: ...


class ConstructionConsultantEvidence(Protocol):
    def collect(self, owner_identity_id: str, question: str) -> tuple[GatewayResponse, ...]: ...


class LocalQwenConstructionConsultantModel:
    def __init__(self, endpoint: str) -> None:
        if not endpoint.startswith(("http://127.0.0.1:", "http://localhost:")):
            raise ValueError("construction_consultant_qwen_endpoint_invalid")
        self._endpoint = endpoint

    def complete(self, prompt: str) -> str:
        request = urllib.request.Request(
            self._endpoint,
            data=json.dumps(
                {
                    "prompt": prompt,
                    "max_tokens": 700,
                    "temperature": 0.2,
                },
                ensure_ascii=False,
            ).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        chunks: list[str] = []
        completed = False
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        try:
            with opener.open(request, timeout=900) as response:
                while line := response.readline():
                    event = json.loads(line)
                    if event.get("event") == "delta":
                        chunks.append(str(event.get("text", "")))
                    elif event.get("event") == "completed":
                        completed = True
                        break
        except (
            urllib.error.URLError,
            urllib.error.HTTPError,
            TimeoutError,
            OSError,
            IncompleteRead,
            RemoteDisconnected,
            json.JSONDecodeError,
        ) as exc:
            raise ConstructionConsultantQuestionError(
                "construction_consultant_inference_unavailable"
            ) from exc
        answer = "".join(chunks).strip()
        if not completed or not answer:
            raise ConstructionConsultantQuestionError(
                "construction_consultant_inference_incomplete"
            )
        return answer


@dataclass(frozen=True, slots=True)
class ConstructionConsultantAnswer:
    user_message: ConstructionConsultantMessage
    assistant_message: ConstructionConsultantMessage
    evidence_statuses: tuple[str, ...]


class ConstructionConsultantQuestionService:
    def __init__(
        self,
        history: ConstructionConsultantHistory,
        repository: ConstructionConsultantMessageStore,
        collector: ConstructionConsultantEvidence,
        model: ConstructionConsultantModel,
    ) -> None:
        self._history = history
        self._repository = repository
        self._collector = collector
        self._model = model

    def ask(
        self,
        *,
        owner_identity_id: str,
        conversation_id: UUID,
        request_id: UUID,
        question: str,
    ) -> ConstructionConsultantAnswer:
        normalized_question = " ".join(question.split())
        if not (2 <= len(normalized_question) <= 8000):
            raise ConstructionConsultantQuestionError("construction_consultant_question_invalid")
        organization_id = self._history.organization_id(owner_identity_id)
        existing = self._repository.messages_for_request(
            organization_id, conversation_id, owner_identity_id, request_id
        )
        existing_user = next((item for item in existing if item.role == "user"), None)
        existing_answer = next((item for item in existing if item.role == "assistant"), None)
        if existing_answer is not None and existing_user is not None:
            return ConstructionConsultantAnswer(existing_user, existing_answer, ())
        history = self._history.messages(owner_identity_id, conversation_id)
        evidence = self._collector.collect(owner_identity_id, normalized_question)
        answer_text = self._model.complete(_prompt(normalized_question, history, evidence))
        sources = _sources(evidence)
        try:
            user_message = existing_user or self._repository.append_message(
                organization_id,
                conversation_id,
                owner_identity_id,
                "user",
                normalized_question,
                request_id=request_id,
            )
            assistant_message = self._repository.append_message(
                organization_id,
                conversation_id,
                owner_identity_id,
                "assistant",
                answer_text,
                sources=sources,
                model_identity="Qwen3.8-27B-MLX-8bit",
                model_profile_version=CONSTRUCTION_CONSULTANT_MODEL_PROFILE,
                request_id=request_id,
            )
        except Exception as exc:
            persisted = self._repository.messages_for_request(
                organization_id, conversation_id, owner_identity_id, request_id
            )
            persisted_user = next((item for item in persisted if item.role == "user"), None)
            persisted_answer = next((item for item in persisted if item.role == "assistant"), None)
            if persisted_user is not None and persisted_answer is not None:
                return ConstructionConsultantAnswer(persisted_user, persisted_answer, ())
            raise ConstructionConsultantQuestionError(
                "construction_consultant_persistence_uncertain"
            ) from exc
        return ConstructionConsultantAnswer(
            user_message,
            assistant_message,
            tuple(response.status.value for response in evidence),
        )


def _sources(responses: tuple[GatewayResponse, ...]) -> tuple[dict[str, Any], ...]:
    values: list[dict[str, Any]] = []
    seen: set[str] = set()
    for response in responses:
        source_views = {
            str(source.get("source_version_id") or source.get("source_id")): source
            for source in response.result.get("sources", [])
            if isinstance(source, dict)
        }
        for item in response.evidence_pack.evidence:
            key = item.evidence_link_id
            if key in seen:
                continue
            seen.add(key)
            source_view = source_views.get(item.source_version_id, {})
            values.append(
                {
                    "source_id": item.source_version_id,
                    "locator": item.structural_unit_locator,
                    "access_reference": item.access_reference,
                    "authority_layer": item.authority_layer,
                    "tool": response.tool,
                    "title": source_view.get("title", item.source_version_id),
                    "href": source_view.get("href", item.access_reference),
                    "edition": source_view.get("edition"),
                    "fragment": source_view.get("fragment"),
                }
            )
    return tuple(values)


def _prompt(
    question: str,
    history: tuple[ConstructionConsultantMessage, ...],
    evidence: tuple[GatewayResponse, ...],
) -> str:
    recent_history = [{"role": item.role, "content": item.content[:1200]} for item in history[-10:]]
    evidence_payload = [
        {
            "tool": response.tool,
            "status": response.status.value,
            "result": response.result,
            "sources": [
                {
                    "source_version_id": item.source_version_id,
                    "locator": item.structural_unit_locator,
                    "access_reference": item.access_reference,
                    "authority_layer": item.authority_layer,
                }
                for item in response.evidence_pack.evidence
            ],
        }
        for response in evidence
    ]
    rendered = json.dumps(evidence_payload, ensure_ascii=False)[:24000]
    return (
        "Вы — Строительный консультант АСД-КОНТУР. Дайте прямой профессиональный ответ "
        "по-русски. Сначала ответ, затем только существенные условия и ограничение. "
        "Не упоминайте ОКС, workspace, внутренние инструменты или Markdown-заголовки. "
        "Инженерную оценку обозначайте как оценку; измеренный факт или нормативное требование "
        "утверждайте только при поддержке источником. Не выдумывайте факты.\n\n"
        f"Вопрос: {question}\nИстория: {json.dumps(recent_history, ensure_ascii=False)}\n"
        f"Проверяемые основания: {rendered}\nПрофиль: {CONSTRUCTION_CONSULTANT_PROFILE}"
    )
