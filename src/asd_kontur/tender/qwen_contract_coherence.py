"""Local-Qwen review of contradictions introduced by proposed contract wording.

The review is a bounded candidate, never an approval of the full contract.
All identifiers, exact quotes and source bindings are checked deterministically.
"""

# ruff: noqa: RUF001 -- Russian professional prompt and output are intentional.

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from asd_kontur.application_spine.models import semantic_digest
from asd_kontur.document_understanding.qwen_semantic import QwenSemanticFailure, _complete
from asd_kontur.tender.contract_coherence import CONTRACT_COHERENCE_PROFILE

CONTRACT_COHERENCE_CONTRACT = "contract-revision-coherence-candidate@1.0.0"


class QwenContractCoherenceReviewer:
    def __init__(self, endpoint: str, *, timeout_seconds: float = 900.0) -> None:
        if not endpoint.startswith(("http://127.0.0.1:", "http://localhost:")):
            raise ValueError("qwen_contract_coherence_endpoint_invalid")
        self._endpoint = endpoint
        self._timeout_seconds = timeout_seconds

    def review(self, context: Mapping[str, Any]) -> dict[str, object]:
        related = context.get("related_clauses")
        proposed = str(context.get("proposed_text") or "")
        source = context.get("source_clause")
        if (
            not isinstance(related, list)
            or not 1 <= len(related) <= 12
            or not isinstance(source, dict)
            or not proposed.strip()
            or str(context.get("profile")) != CONTRACT_COHERENCE_PROFILE
            or semantic_digest({k: v for k, v in context.items() if k != "context_digest"})
            != context.get("context_digest")
        ):
            raise QwenSemanticFailure("qwen_contract_coherence_input_invalid")
        prompt = _review_prompt(context)
        raw = _complete(self._endpoint, prompt, self._timeout_seconds, max_tokens=2600)
        try:
            conflicts = parse_contract_coherence(raw, context=context)
        except QwenSemanticFailure as exc:
            repaired = _complete(
                self._endpoint,
                _repair_prompt(context, raw[:3_000], exc.code),
                self._timeout_seconds,
                max_tokens=2600,
            )
            conflicts = parse_contract_coherence(repaired, context=context)
        result: dict[str, object] = {
            "contract": CONTRACT_COHERENCE_CONTRACT,
            "profile_version": CONTRACT_COHERENCE_PROFILE,
            "context_digest": str(context["context_digest"]),
            "revision_id": str(context["revision_id"]),
            "revision_digest": str(context["revision_digest"]),
            "source_clause_id": str(source["clause_id"]),
            "source_version_id": str(source["source_version_id"]),
            "source_locator_id": str(source.get("source_locator_id") or ""),
            "review_scope": "selected_related_clauses_only",
            "coverage": context["coverage"],
            "conflicts": conflicts,
        }
        result["result_digest"] = semantic_digest(result)
        return result


def parse_contract_coherence(raw: str, *, context: Mapping[str, Any]) -> list[dict[str, object]]:
    try:
        decoded = json.loads(raw)
    except (TypeError, ValueError) as exc:
        raise QwenSemanticFailure("qwen_contract_coherence_invalid_json") from exc
    if not isinstance(decoded, dict) or not isinstance(decoded.get("conflicts"), list):
        raise QwenSemanticFailure("qwen_contract_coherence_invalid_shape")
    items = decoded["conflicts"]
    if len(items) > 8:
        raise QwenSemanticFailure("qwen_contract_coherence_too_many_conflicts")
    proposal = str(context.get("proposed_text") or "")
    related = {
        str(item.get("clause_id")): item
        for item in context.get("related_clauses") or ()
        if isinstance(item, dict)
    }
    accepted: list[dict[str, object]] = []
    seen: set[str] = set()
    for item in items:
        if not isinstance(item, dict):
            raise QwenSemanticFailure("qwen_contract_coherence_invalid_item")
        other_id = str(item.get("other_clause_id") or "")
        other = related.get(other_id)
        proposal_quote = str(item.get("proposal_quote") or "")
        other_quote = str(item.get("other_quote") or "")
        confidence = item.get("confidence")
        if (
            other is None
            or other_id in seen
            or not proposal_quote
            or not other_quote
            or _normalize(proposal_quote) not in _normalize(proposal)
            or _normalize(other_quote) not in _normalize(str(other.get("source_text") or ""))
            or isinstance(confidence, bool)
            or not isinstance(confidence, (int, float))
            or not 0 <= float(confidence) <= 1
        ):
            raise QwenSemanticFailure("qwen_contract_coherence_source_invalid")
        narrative = {
            key: str(item.get(key) or "").strip()
            for key in ("conflict", "contractor_consequence", "recommended_action")
        }
        if any(not value or len(value) > 800 for value in narrative.values()):
            raise QwenSemanticFailure("qwen_contract_coherence_invalid_item")
        seen.add(other_id)
        accepted.append(
            {
                "other_clause_id": other_id,
                "other_source_version_id": str(other.get("source_version_id") or ""),
                "other_source_locator_id": str(other.get("source_locator_id") or ""),
                "proposal_quote": proposal_quote,
                "other_quote": other_quote,
                **narrative,
                "confidence": float(confidence),
                "uncertainty": str(item.get("uncertainty") or "").strip() or None,
            }
        )
    return accepted


def _normalize(value: str) -> str:
    return " ".join(value.split())


def _review_prompt(context: Mapping[str, Any]) -> str:
    payload = {
        "revision_id": context["revision_id"],
        "original_clause": context["source_clause"],
        "proposed_contractor_wording": context["proposed_text"],
        "related_clauses": context["related_clauses"],
    }
    return (
        "Проверь только прямые содержательные противоречия между предложенной редакцией "
        "пункта строительного договора и предоставленными связанными пунктами. "
        "Не утверждай, что проверен весь договор. Не выдумывай нормы права, сроки или суммы. "
        "Обычное выгодное Заказчику условие само по себе не противоречие. "
        'Верни только JSON: {"conflicts":[{"other_clause_id":"точный id из входа",'
        '"proposal_quote":"точная цитата из proposed_contractor_wording",'
        '"other_quote":"точная цитата из связанного пункта",'
        '"conflict":"профессиональное объяснение",'
        '"contractor_consequence":"практическое последствие",'
        '"recommended_action":"что согласовать","confidence":0.0,'
        '"uncertainty":null}]}. Если доказанного противоречия нет, верни '
        '{"conflicts":[]}. Вход: ' + json.dumps(payload, ensure_ascii=False, sort_keys=True)
    )


def _repair_prompt(context: Mapping[str, Any], raw: str, error_code: str) -> str:
    return (
        _review_prompt(context)
        + "\nПредыдущий ответ отклонён валидатором: "
        + error_code
        + ". Исправь JSON, сохрани только подтверждённые точными цитатами выводы. "
        + "Предыдущий ответ: "
        + raw
    )
