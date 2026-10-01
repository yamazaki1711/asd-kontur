"""Bounded contractor-oriented interpretation of contract clauses by local Qwen.

The model determines meaning and drafts professional language. Exact source text,
identities, persistence and all numeric/date arithmetic remain deterministic.
"""

# ruff: noqa: E501, RUF001 -- Russian product prompts are intentionally literal.

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping

from asd_kontur.application_spine.models import semantic_digest
from asd_kontur.document_understanding.qwen_semantic import QwenSemanticFailure, _complete

CONTRACT_ANALYSIS_PROFILE = "qwen-contract-analysis-v1"
CONTRACT_ANALYSIS_CONTRACT = "contract-analysis-candidate@1.0.0"
_CLAUSE_CATEGORIES = frozenset(
    {
        "scope",
        "customer_obligation",
        "contractor_obligation",
        "deadline",
        "payment",
        "price",
        "acceptance",
        "liability",
        "warranty",
        "change_procedure",
        "termination",
        "security",
        "insurance",
        "documentation",
        "other",
    }
)
_RISK_KINDS = frozenset(
    {
        "payment_dependency",
        "uncontrolled_obligation",
        "unclear_acceptance",
        "unpaid_change",
        "deadline_exposure",
        "one_sided_liability",
        "excessive_warranty",
        "unlimited_liability",
        "asymmetric_termination",
        "missing_price_adjustment",
        "customer_input_dependency",
        "open_ended_documentation",
        "project_contract_conflict",
        "other_contract_risk",
    }
)
_SEVERITIES = frozenset({"low", "medium", "high", "critical"})


class QwenContractAnalyzer:
    """Analyze one bounded exact-source contract context through local Qwen."""

    def __init__(self, endpoint: str, *, timeout_seconds: float = 900.0) -> None:
        if not endpoint.startswith(("http://127.0.0.1:", "http://localhost:")):
            raise ValueError("qwen_contract_analysis_endpoint_invalid")
        self._endpoint = endpoint
        self._timeout_seconds = timeout_seconds

    def analyze(self, fragments: Iterable[Mapping[str, object]]) -> dict[str, object]:
        values = [dict(item) for item in fragments]
        if not 1 <= len(values) <= 32:
            raise QwenSemanticFailure("qwen_contract_analysis_batch_size_invalid")
        allowed: dict[str, str] = {}
        prompt_rows: list[dict[str, object]] = []
        total_chars = 0
        for item in values:
            locator_id = str(item.get("source_locator_id") or "")
            text = " ".join(str(item.get("text") or "").split())
            if not locator_id or not text or locator_id in allowed:
                raise QwenSemanticFailure("qwen_contract_analysis_input_invalid")
            total_chars += len(text)
            if total_chars > 12_000:
                raise QwenSemanticFailure("qwen_contract_analysis_context_too_large")
            allowed[locator_id] = text
            prompt_rows.append(
                {
                    "source_locator_id": locator_id,
                    "page": item.get("page"),
                    "text": text,
                }
            )
        prompt = _prompt(prompt_rows)
        raw = _complete(
            self._endpoint,
            prompt,
            self._timeout_seconds,
            max_tokens=max(1800, min(5000, 700 + len(prompt_rows) * 180)),
        )
        try:
            parsed = parse_contract_analysis(raw, allowed_text_by_locator=allowed)
        except QwenSemanticFailure as exc:
            if not exc.code.startswith("qwen_contract_"):
                raise
            repaired = _complete(
                self._endpoint,
                _repair_prompt(prompt_rows, raw, exc.code),
                self._timeout_seconds,
                max_tokens=max(1800, min(5000, 700 + len(prompt_rows) * 180)),
            )
            parsed = parse_contract_analysis(repaired, allowed_text_by_locator=allowed)
        result: dict[str, object] = {
            "contract": CONTRACT_ANALYSIS_CONTRACT,
            "profile_version": CONTRACT_ANALYSIS_PROFILE,
            **parsed,
        }
        result["result_digest"] = semantic_digest(result)
        return result


def parse_contract_analysis(
    raw: str, *, allowed_text_by_locator: Mapping[str, str]
) -> dict[str, object]:
    """Validate model JSON against exact bounded input identities and source text."""

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise QwenSemanticFailure("qwen_contract_analysis_invalid_json") from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("clauses"), list):
        raise QwenSemanticFailure("qwen_contract_analysis_invalid_shape")
    clauses: list[dict[str, object]] = []
    seen_clause_ids: set[str] = set()
    for index, raw_clause in enumerate(payload["clauses"], start=1):
        if not isinstance(raw_clause, dict):
            raise QwenSemanticFailure("qwen_contract_clause_invalid")
        clause_ref = str(raw_clause.get("clause_ref") or f"batch-{index}").strip()
        locator_ids = raw_clause.get("source_locator_ids")
        source_text = " ".join(str(raw_clause.get("source_text") or "").split())
        category = str(raw_clause.get("category") or "")
        if (
            not clause_ref
            or clause_ref in seen_clause_ids
            or not isinstance(locator_ids, list)
            or not locator_ids
            or category not in _CLAUSE_CATEGORIES
        ):
            raise QwenSemanticFailure("qwen_contract_clause_invalid")
        normalized_locators = [str(value) for value in locator_ids]
        if any(value not in allowed_text_by_locator for value in normalized_locators):
            raise QwenSemanticFailure("qwen_contract_clause_evidence_invalid")
        allowed_source = " ".join(allowed_text_by_locator[value] for value in normalized_locators)
        if not source_text or source_text.casefold() not in allowed_source.casefold():
            raise QwenSemanticFailure("qwen_contract_clause_source_not_exact")
        seen_clause_ids.add(clause_ref)
        clauses.append(
            {
                "clause_ref": clause_ref,
                "section": _optional_text(raw_clause.get("section")),
                "source_text": source_text,
                "source_locator_ids": normalized_locators,
                "category": category,
                "customer_obligation": _optional_text(raw_clause.get("customer_obligation")),
                "contractor_obligation": _optional_text(raw_clause.get("contractor_obligation")),
                "condition": _optional_text(raw_clause.get("condition")),
            }
        )
    risks_raw = payload.get("risks", [])
    if not isinstance(risks_raw, list):
        raise QwenSemanticFailure("qwen_contract_risks_invalid")
    risks: list[dict[str, object]] = []
    for raw_risk in risks_raw:
        if not isinstance(raw_risk, dict):
            raise QwenSemanticFailure("qwen_contract_risk_invalid")
        clause_ref = str(raw_risk.get("clause_ref") or "")
        kind = str(raw_risk.get("kind") or "")
        severity = str(raw_risk.get("severity") or "")
        confidence = raw_risk.get("confidence")
        if (
            clause_ref not in seen_clause_ids
            or kind not in _RISK_KINDS
            or severity not in _SEVERITIES
            or not isinstance(confidence, (int, float))
            or not 0 <= float(confidence) <= 1
        ):
            raise QwenSemanticFailure("qwen_contract_risk_invalid")
        required = ("description", "practical_consequence", "recommended_action")
        if any(not _optional_text(raw_risk.get(key)) for key in required):
            raise QwenSemanticFailure("qwen_contract_risk_invalid")
        disagreement = raw_risk.get("disagreement_required")
        proposed = _optional_text(raw_risk.get("proposed_contractor_wording"))
        if not isinstance(disagreement, bool) or (disagreement and not proposed):
            raise QwenSemanticFailure("qwen_contract_risk_revision_invalid")
        risks.append(
            {
                "clause_ref": clause_ref,
                "kind": kind,
                "severity": severity,
                "description": _optional_text(raw_risk.get("description")),
                "practical_consequence": _optional_text(raw_risk.get("practical_consequence")),
                "recommended_action": _optional_text(raw_risk.get("recommended_action")),
                "proposed_contractor_wording": proposed,
                "disagreement_required": disagreement,
                "confidence": float(confidence),
                "uncertainty": _optional_text(raw_risk.get("uncertainty")),
                "authority": "contract_commercial_risk",
            }
        )
    return {"clauses": clauses, "risks": risks}


def _optional_text(value: object) -> str | None:
    normalized = " ".join(str(value or "").split())
    return normalized or None


def _prompt(rows: list[dict[str, object]]) -> str:
    return f"""Ты анализируешь ограниченный фрагмент договора строительного подряда с позиции коммерческих рисков Подрядчика.
Источник истины — только CONTEXT. Не придумывай пункты, цифры, сроки, нормы права или факты проекта.
Выдели самостоятельные условия договора. source_text должен быть дословной непрерывной цитатой из одного или нескольких указанных фрагментов (нормализация пробелов допустима).
Оценивай практический риск: исполнимость обязательства, зависимость оплаты/приёмки от Заказчика, изменение объёмов и РД, сроки, ответственность, гарантию, расторжение и исходные данные.
Обычные сбалансированные условия не отмечай как риск. Не выдавай коммерческую оценку за подтверждённое юридическое заключение.
Если нужна редакция Подрядчика, она должна быть конкретной и соответствовать исходному пункту.

Верни только JSON:
{{"clauses":[{{"clause_ref":"номер или локальная метка","section":"раздел или null","source_text":"точная цитата","source_locator_ids":["id"],"category":"scope|customer_obligation|contractor_obligation|deadline|payment|price|acceptance|liability|warranty|change_procedure|termination|security|insurance|documentation|other","customer_obligation":"... или null","contractor_obligation":"... или null","condition":"... или null"}}],"risks":[{{"clause_ref":"ссылка на clause_ref","kind":"payment_dependency|uncontrolled_obligation|unclear_acceptance|unpaid_change|deadline_exposure|one_sided_liability|excessive_warranty|unlimited_liability|asymmetric_termination|missing_price_adjustment|customer_input_dependency|open_ended_documentation|project_contract_conflict|other_contract_risk","severity":"low|medium|high|critical","description":"что неясно или опасно","practical_consequence":"практическое последствие для Подрядчика","recommended_action":"что уточнить или изменить","proposed_contractor_wording":"конкретная редакция или null","disagreement_required":true,"confidence":0.0,"uncertainty":"... или null"}}]}}

CONTEXT:
{json.dumps(rows, ensure_ascii=False, separators=(",", ":"))}
"""


def _repair_prompt(rows: list[dict[str, object]], invalid: str, failure_code: str) -> str:
    return (
        _prompt(rows)
        + "\nПредыдущий ответ отклонён валидатором: "
        + failure_code
        + ". Исправь только JSON и ссылки на предоставленные source_locator_id. "
        + "Не добавляй новых фактов.\nINVALID_RESPONSE:\n"
        + invalid[:12_000]
    )
