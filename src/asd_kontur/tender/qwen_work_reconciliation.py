"""Bounded local-Qwen interpretation of unresolved construction work descriptions."""

# ruff: noqa: RUF001 -- Russian construction prompt terms are intentional.

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from decimal import Decimal, InvalidOperation
from typing import Any

from asd_kontur.application_spine.models import semantic_digest
from asd_kontur.document_understanding.qwen_semantic import QwenSemanticFailure, _complete

PROJECT_WORK_RECONCILIATION_PROFILE = "qwen-project-work-reconciliation-v1"
WORK_RECONCILIATION_CONTRACT = "project-work-reconciliation-result@1.0.0"
_STATUSES = frozenset({"MATCHED", "AMBIGUOUS", "UNCLASSIFIED", "NOT_A_WORK"})


class QwenProjectWorkReconciler:
    """Interpret only bounded unresolved rows; deterministic code owns validation."""

    def __init__(self, endpoint: str, *, timeout_seconds: float = 900.0) -> None:
        if not endpoint.startswith(("http://127.0.0.1:", "http://localhost:")):
            raise ValueError("qwen_work_reconciliation_endpoint_invalid")
        self._endpoint = endpoint
        self._timeout_seconds = timeout_seconds

    def reconcile(
        self,
        rows: Iterable[Mapping[str, Any]],
        *,
        work_families: Mapping[str, str],
        facilities: Iterable[str],
    ) -> dict[str, Any]:
        input_rows = [dict(row) for row in rows]
        if not 1 <= len(input_rows) <= 16:
            raise QwenSemanticFailure("qwen_work_reconciliation_batch_size_invalid")
        input_ids = [str(row.get("candidate_id") or "") for row in input_rows]
        if any(not value for value in input_ids) or len(set(input_ids)) != len(input_ids):
            raise QwenSemanticFailure("qwen_work_reconciliation_input_identity_invalid")
        allowed_facilities = tuple(dict.fromkeys(str(value) for value in facilities if value))
        prompt = _prompt(input_rows, work_families, allowed_facilities)
        raw = _complete(
            self._endpoint,
            prompt,
            self._timeout_seconds,
            max_tokens=max(900, min(3_200, len(input_rows) * 170)),
        )
        observations = _parse(
            raw,
            input_ids=tuple(input_ids),
            work_families=work_families,
            facilities=allowed_facilities,
        )
        manifest = {
            "contract": WORK_RECONCILIATION_CONTRACT,
            "profile_version": PROJECT_WORK_RECONCILIATION_PROFILE,
            "observations": observations,
        }
        manifest["result_digest"] = semantic_digest(manifest)
        return manifest


def _prompt(
    rows: list[dict[str, Any]], work_families: Mapping[str, str], facilities: tuple[str, ...]
) -> str:
    safe_rows = [
        {
            "candidate_id": str(row["candidate_id"]),
            "wording": str(row.get("wording") or "")[:700],
            "document_role": str(row.get("document_role") or "не определена"),
            "document": str(row.get("document") or "")[:180],
            "page": row.get("page"),
            "scope": str(row.get("scope") or "")[:240],
            "facility_hints": list(row.get("facility_hints") or ())[:6],
            "nearby_context": str(row.get("nearby_context") or "")[:900],
        }
        for row in rows
    ]
    return f"""Вы анализируете извлечённые описания российского строительного проекта.
Для КАЖДОЙ входной строки определите, является ли она строительной операцией, к какому виду работ
относится и можно ли привязать её к одному сооружению. Не придумывайте отсутствующие работы,
сооружения, объёмы или материалы. Совпадение по одному слову недостаточно. Перевозка, погрузка,
испытание и временная операция могут быть отдельной коммерческой работой; материал, заголовок,
техническая характеристика и функция оборудования не являются работой.

Допустимые family_key: {json.dumps(dict(work_families), ensure_ascii=False)}
Допустимые сооружения: {json.dumps(facilities, ensure_ascii=False)}
Строки: {json.dumps(safe_rows, ensure_ascii=False)}

Верните только JSON:
{{"observations":[{{"candidate_id":"...","status":"MATCHED|AMBIGUOUS|UNCLASSIFIED|NOT_A_WORK",
"family_key":"ключ или null","operation":"краткое профессиональное название или null",
"facility":"одно допустимое сооружение или null","confidence":"0.00..1.00",
"reason":"краткая инженерная причина"}}]}}
Верните ровно одну запись для каждого candidate_id, без новых идентификаторов. MATCHED требует один
family_key. AMBIGUOUS/UNCLASSIFIED не должны угадывать family_key. Facility допустим только при
явной привязке из текста или контекста; нахождение в одном документе недостаточно.
"""


def _parse(
    raw: str,
    *,
    input_ids: tuple[str, ...],
    work_families: Mapping[str, str],
    facilities: tuple[str, ...],
) -> list[dict[str, Any]]:
    text = raw.strip()
    if text.startswith("```"):
        text = text.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise QwenSemanticFailure("qwen_work_reconciliation_invalid_json") from exc
    values = payload.get("observations") if isinstance(payload, dict) else None
    if not isinstance(values, list):
        raise QwenSemanticFailure("qwen_work_reconciliation_invalid_shape")
    if len(values) != len(input_ids):
        raise QwenSemanticFailure("qwen_work_reconciliation_incomplete_output")
    allowed_ids = set(input_ids)
    allowed_families = set(work_families)
    allowed_facilities = set(facilities)
    observations: dict[str, dict[str, Any]] = {}
    for value in values:
        if not isinstance(value, dict):
            raise QwenSemanticFailure("qwen_work_reconciliation_invalid_shape")
        candidate_id = str(value.get("candidate_id") or "")
        status = str(value.get("status") or "")
        family = value.get("family_key")
        family_key = str(family) if family is not None else None
        operation = str(value.get("operation") or "").strip() or None
        facility = str(value.get("facility") or "").strip() or None
        reason = " ".join(str(value.get("reason") or "").split())
        try:
            confidence = Decimal(str(value.get("confidence")))
        except (InvalidOperation, TypeError) as exc:
            raise QwenSemanticFailure("qwen_work_reconciliation_confidence_invalid") from exc
        if candidate_id not in allowed_ids or candidate_id in observations:
            raise QwenSemanticFailure("qwen_work_reconciliation_identity_invalid")
        if status not in _STATUSES or not Decimal("0") <= confidence <= Decimal("1") or not reason:
            raise QwenSemanticFailure("qwen_work_reconciliation_observation_invalid")
        if status == "MATCHED":
            if family_key not in allowed_families or operation is None:
                raise QwenSemanticFailure("qwen_work_reconciliation_family_invalid")
        elif family_key is not None:
            raise QwenSemanticFailure("qwen_work_reconciliation_unresolved_family_invalid")
        if facility is not None and facility not in allowed_facilities:
            raise QwenSemanticFailure("qwen_work_reconciliation_facility_invalid")
        observations[candidate_id] = {
            "candidate_id": candidate_id,
            "status": status,
            "family_key": family_key,
            "operation": operation,
            "facility": facility,
            "confidence": format(confidence, "f"),
            "reason": reason[:500],
        }
    if set(observations) != allowed_ids:
        raise QwenSemanticFailure("qwen_work_reconciliation_incomplete_output")
    return [observations[candidate_id] for candidate_id in input_ids]
