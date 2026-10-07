"""Bounded, source-grounded review of documents referenced by a contract.

This is a semantic routing task, not a legal conclusion.  A reference that is
not matched to the admitted inventory remains a clarification candidate; it is
not proof that the counterparty omitted the attachment.
"""

# ruff: noqa: RUF001 -- Russian production prompts intentionally contain Cyrillic.

from __future__ import annotations

import json
import re
from collections.abc import Iterable, Mapping
from typing import cast

from asd_kontur.application_spine.models import semantic_digest
from asd_kontur.document_understanding.qwen_semantic import QwenSemanticFailure, _complete

CONTRACT_REFERENCE_PROFILE = "qwen-contract-references-v1"
CONTRACT_REFERENCE_CONTRACT = "contract-references-candidate@1.0.0"
_REFERENCE_KINDS = frozenset(
    {"attachment", "technical_assignment", "schedule", "estimate", "drawing", "other"}
)
_MATCH_DECISIONS = frozenset({"matched", "unresolved"})
_MAX_CONTEXT_CHARS = 9_000
_MAX_INVENTORY = 64
_REFERENCE_SIGNAL = re.compile(
    r"(?:приложени\w*|техническ\w*\s+задан\w*|график\w*|ведомост\w*|"
    r"чертеж\w*|спецификац\w*|appendix|annex|attachment|schedule|drawing|"
    r"technical\s+specification)",
    flags=re.IGNORECASE,
)


def reference_context_candidate(text: str) -> bool:
    """Route likely cross-references to Qwen; never decide their meaning here."""

    return bool(_REFERENCE_SIGNAL.search(text))


class QwenContractReferenceReviewer:
    """Ask the persistent local model what an exact contract reference means."""

    def __init__(self, endpoint: str, *, timeout_seconds: float = 900.0) -> None:
        if not endpoint.startswith(("http://127.0.0.1:", "http://localhost:")):
            raise ValueError("qwen_contract_reference_endpoint_invalid")
        self._endpoint = endpoint
        self._timeout_seconds = timeout_seconds

    def review(
        self,
        fragments: Iterable[Mapping[str, object]],
        *,
        admitted_sources: Iterable[Mapping[str, object]],
    ) -> dict[str, object]:
        rows = [dict(row) for row in fragments]
        sources = [dict(source) for source in admitted_sources]
        if not rows or not sources or len(sources) > _MAX_INVENTORY:
            raise QwenSemanticFailure("qwen_contract_reference_input_invalid")
        allowed_text: dict[str, str] = {}
        prompt_rows: list[dict[str, object]] = []
        for row in rows:
            locator = str(row.get("source_locator_id") or "")
            value = " ".join(str(row.get("text") or "").split())
            if not locator or not value or locator in allowed_text:
                raise QwenSemanticFailure("qwen_contract_reference_input_invalid")
            allowed_text[locator] = value
            prompt_rows.append(
                {"source_locator_id": locator, "page": row.get("page"), "text": value}
            )
        inventory: dict[str, str] = {}
        for source in sources:
            source_id = str(source.get("source_version_id") or "")
            title = " ".join(str(source.get("safe_display_name") or "").split())
            if not source_id or not title or source_id in inventory:
                raise QwenSemanticFailure("qwen_contract_reference_inventory_invalid")
            inventory[source_id] = title
        if sum(map(len, allowed_text.values())) > _MAX_CONTEXT_CHARS:
            raise QwenSemanticFailure("qwen_contract_reference_context_too_large")
        prompt = _prompt(prompt_rows, inventory)
        try:
            raw = _complete(self._endpoint, prompt, self._timeout_seconds, max_tokens=3000)
        except QwenSemanticFailure as exc:
            if exc.code != "qwen_semantic_response_output_exhausted" or len(rows) < 2:
                raise
            midpoint = len(rows) // 2
            left = self.review(rows[:midpoint], admitted_sources=sources)
            right = self.review(rows[midpoint:], admitted_sources=sources)
            merged: dict[str, object] = {
                "contract": CONTRACT_REFERENCE_CONTRACT,
                "profile_version": CONTRACT_REFERENCE_PROFILE,
                "references": [
                    *cast(list[dict[str, object]], left["references"]),
                    *cast(list[dict[str, object]], right["references"]),
                ],
            }
            merged["result_digest"] = semantic_digest(merged)
            return merged
        try:
            parsed = parse_contract_references(raw, allowed_text=allowed_text, inventory=inventory)
        except QwenSemanticFailure as exc:
            if exc.code not in {
                "qwen_contract_reference_invalid_json",
                "qwen_contract_reference_invalid_shape",
                "qwen_contract_reference_invalid_item",
            }:
                raise
            repair = _complete(
                self._endpoint,
                prompt
                + "\nОтвет отклонён: "
                + exc.code
                + ". Исправь только JSON без новых фактов.\n"
                + raw[:5000],
                self._timeout_seconds,
                max_tokens=3000,
            )
            parsed = parse_contract_references(
                repair, allowed_text=allowed_text, inventory=inventory
            )
        result: dict[str, object] = {
            "contract": CONTRACT_REFERENCE_CONTRACT,
            "profile_version": CONTRACT_REFERENCE_PROFILE,
            "references": parsed,
        }
        result["result_digest"] = semantic_digest(result)
        return result


def parse_contract_references(
    raw: str,
    *,
    allowed_text: Mapping[str, str],
    inventory: Mapping[str, str],
) -> list[dict[str, object]]:
    """Reject invented source quotes, identities and internally inconsistent matches."""

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise QwenSemanticFailure("qwen_contract_reference_invalid_json") from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("references"), list):
        raise QwenSemanticFailure("qwen_contract_reference_invalid_shape")
    output: list[dict[str, object]] = []
    seen: set[tuple[str, str]] = set()
    for item in payload["references"]:
        if not isinstance(item, dict):
            raise QwenSemanticFailure("qwen_contract_reference_invalid_item")
        locator = str(item.get("source_locator_id") or "")
        quote = " ".join(str(item.get("source_quote") or "").split())
        target = " ".join(str(item.get("target_description") or "").split())
        kind = str(item.get("kind") or "")
        decision = str(item.get("match_decision") or "")
        source_id = item.get("matched_source_version_id")
        confidence = item.get("confidence")
        if (
            locator not in allowed_text
            or not quote
            or quote.casefold() not in allowed_text[locator].casefold()
            or not target
            or kind not in _REFERENCE_KINDS
            or decision not in _MATCH_DECISIONS
            or not isinstance(confidence, (int, float))
            or isinstance(confidence, bool)
            or not 0 <= float(confidence) <= 1
            or (decision == "matched" and str(source_id or "") not in inventory)
            or (decision == "unresolved" and source_id is not None)
        ):
            raise QwenSemanticFailure("qwen_contract_reference_invalid_item")
        identity = (locator, quote.casefold())
        if identity in seen:
            raise QwenSemanticFailure("qwen_contract_reference_invalid_item")
        seen.add(identity)
        output.append(
            {
                "source_locator_id": locator,
                "source_quote": quote,
                "target_description": target,
                "kind": kind,
                "match_decision": decision,
                "matched_source_version_id": str(source_id) if source_id is not None else None,
                "matched_source_name": inventory[str(source_id)] if source_id is not None else None,
                "confidence": float(confidence),
                "uncertainty": str(item.get("uncertainty") or "").strip() or None,
            }
        )
    return output


def _prompt(rows: list[dict[str, object]], inventory: Mapping[str, str]) -> str:
    return (
        "Ты проверяешь только ссылки строительного договора на другие документы. "
        "CONTEXT — ограниченный точный текст договора. INVENTORY — все принятые документы "
        "проекта, перечисленные для этой задачи. Не считай отсутствие документа доказанным, "
        "если ссылка неоднозначна. Не анализируй риски или право. Найди прямые ссылки на "
        "приложения, техническое задание, графики, сметы, чертежи и другие документы, "
        "от которых зависит исполнение условия. source_quote — непрерывная дословная цитата "
        "из одного source_locator_id. matched допустим только когда конкретный документ "
        "в INVENTORY убедительно соответствует ссылке; иначе unresolved. "
        "Не выбирай документ лишь потому, что тема похожа. Не придумывай название, номер "
        "или идентификатор. Верни только JSON вида "
        '{"references":[{"source_locator_id":"id","source_quote":"точная цитата",'
        '"target_description":"что требуется","kind":"attachment|technical_assignment|'
        'schedule|estimate|drawing|other","match_decision":"matched|unresolved",'
        '"matched_source_version_id":null,"confidence":0.0,"uncertainty":null}]}.'
        "\nCONTEXT:\n"
        + json.dumps(rows, ensure_ascii=False, separators=(",", ":"))
        + "\nINVENTORY:\n"
        + json.dumps(
            [
                {"source_version_id": source_id, "safe_display_name": title}
                for source_id, title in inventory.items()
            ],
            ensure_ascii=False,
            separators=(",", ":"),
        )
    )
