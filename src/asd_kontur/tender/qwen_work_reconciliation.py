"""Bounded local-Qwen interpretation of unresolved construction work descriptions."""

# ruff: noqa: RUF001 -- Russian construction prompt terms are intentional.

from __future__ import annotations

import json
import re
from collections.abc import Iterable, Mapping
from decimal import Decimal, InvalidOperation
from typing import Any

from asd_kontur.application_spine.models import semantic_digest
from asd_kontur.document_understanding.qwen_semantic import QwenSemanticFailure, _complete

PROJECT_WORK_RECONCILIATION_PROFILE = "qwen-project-work-reconciliation-v6"
PROJECT_WORK_RECONCILIATION_COMPATIBLE_PROFILES = (
    "qwen-project-work-reconciliation-v3",
    "qwen-project-work-reconciliation-v4",
    "qwen-project-work-reconciliation-v5",
    PROJECT_WORK_RECONCILIATION_PROFILE,
)
WORK_RECONCILIATION_CONTRACT = "project-work-reconciliation-result@6.0.0"
_STATUSES = frozenset({"MATCHED", "AMBIGUOUS", "UNCLASSIFIED", "NOT_A_WORK"})
_QUANTITY_STATUSES = frozenset(
    {
        "WORK_QUANTITY",
        "DIMENSION",
        "DURATION",
        "RESOURCE_OR_RATE",
        "UNRELATED",
        "AMBIGUOUS",
    }
)
_POTENTIAL_WORK_AT_START = re.compile(
    r"^(?:перевоз\w*|транспортирован\w*|погруз\w*|разгруз\w*|испытан\w*|"
    r"монтаж\w*|демонтаж\w*|геодез\w*|пусконалад\w*)\b",
    re.IGNORECASE,
)
_WEAK_FACILITY_REASON = re.compile(
    r"(?:близост|в том же (?:абзац|контекст)|контекст.*упомина|косвен|предполож|вероятн)",
    re.IGNORECASE,
)
_RECOVERABLE_RESPONSE_FAILURES = frozenset(
    {
        "qwen_work_reconciliation_invalid_json",
        "qwen_work_reconciliation_invalid_shape",
        "qwen_work_reconciliation_incomplete_output",
        "qwen_work_reconciliation_identity_invalid",
        "qwen_work_reconciliation_observation_invalid",
        "qwen_work_reconciliation_family_invalid",
        "qwen_work_reconciliation_unresolved_family_invalid",
        "qwen_work_reconciliation_confidence_invalid",
        "qwen_work_reconciliation_facility_invalid",
        "qwen_work_reconciliation_potential_work_excluded",
        "qwen_work_reconciliation_quantity_output_unexpected",
        "qwen_work_reconciliation_quantity_output_incomplete",
        "qwen_work_reconciliation_quantity_output_invalid",
        "qwen_semantic_response_incomplete",
        "qwen_semantic_response_output_exhausted",
    }
)


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
        observations, call_count, recovery_codes = self._reconcile_rows(
            input_rows,
            work_families=work_families,
            facilities=allowed_facilities,
        )
        manifest = {
            "contract": WORK_RECONCILIATION_CONTRACT,
            "profile_version": PROJECT_WORK_RECONCILIATION_PROFILE,
            "observations": observations,
            "inference_call_count": call_count,
            "recovery_codes": recovery_codes,
        }
        manifest["result_digest"] = semantic_digest(manifest)
        return manifest

    def _reconcile_rows(
        self,
        rows: list[dict[str, Any]],
        *,
        work_families: Mapping[str, str],
        facilities: tuple[str, ...],
        single_retry_available: bool = True,
    ) -> tuple[list[dict[str, Any]], int, list[str]]:
        input_ids = tuple(str(row["candidate_id"]) for row in rows)
        quantity_ids_by_work = {
            str(row["candidate_id"]): tuple(
                str(value.get("quantity_candidate_id") or "")
                for value in row.get("quantity_observations") or ()
                if isinstance(value, Mapping)
            )
            for row in rows
        }
        try:
            quantity_count = sum(len(row.get("quantity_observations") or ()) for row in rows)
            raw = _complete(
                self._endpoint,
                _prompt(rows, work_families, facilities),
                self._timeout_seconds,
                max_tokens=max(900, min(3_200, len(rows) * 170 + quantity_count * 90)),
            )
            return (
                _parse(
                    raw,
                    input_ids=input_ids,
                    wording_by_id={
                        str(row["candidate_id"]): str(row.get("wording") or "").casefold()
                        for row in rows
                    },
                    quantity_ids_by_work=quantity_ids_by_work,
                    work_families=work_families,
                    facilities=facilities,
                ),
                1,
                [],
            )
        except QwenSemanticFailure as exc:
            if exc.code not in _RECOVERABLE_RESPONSE_FAILURES:
                raise
            if len(rows) == 1:
                if not single_retry_available:
                    raise
                observations, call_count, codes = self._reconcile_rows(
                    rows,
                    work_families=work_families,
                    facilities=facilities,
                    single_retry_available=False,
                )
                return observations, call_count + 1, [exc.code, *codes]
            midpoint = len(rows) // 2
            left, left_calls, left_codes = self._reconcile_rows(
                rows[:midpoint],
                work_families=work_families,
                facilities=facilities,
            )
            right, right_calls, right_codes = self._reconcile_rows(
                rows[midpoint:],
                work_families=work_families,
                facilities=facilities,
            )
            return (
                [*left, *right],
                1 + left_calls + right_calls,
                [exc.code, *left_codes, *right_codes],
            )


def _prompt(
    rows: list[dict[str, Any]], work_families: Mapping[str, str], facilities: tuple[str, ...]
) -> str:
    safe_rows = [
        {
            "candidate_id": str(row["candidate_id"]),
            "wording": str(row.get("wording") or ""),
            "document_role": str(row.get("document_role") or "не определена"),
            "document": str(row.get("document") or "")[:180],
            "page": row.get("page"),
            "scope": str(row.get("scope") or "")[:240],
            "facility_hints": list(row.get("facility_hints") or ())[:6],
            "deterministic_family_hint": row.get("deterministic_family_hint"),
            "nearby_context": str(row.get("nearby_context") or ""),
            "nearby_context_locator_ids": list(row.get("nearby_context_locator_ids") or ()),
            "quantity_observations": [
                {
                    "quantity_candidate_id": str(value.get("quantity_candidate_id") or ""),
                    "value": value.get("value"),
                    "unit": value.get("unit"),
                    "source_locator_id": value.get("source_locator_id"),
                    "nearby_context": str(value.get("nearby_context") or ""),
                }
                for value in row.get("quantity_observations") or ()
                if isinstance(value, Mapping)
            ],
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
"reason":"краткая инженерная причина","quantity_reviews":[{{
"quantity_candidate_id":"...","status":"WORK_QUANTITY|DIMENSION|DURATION|RESOURCE_OR_RATE|UNRELATED|AMBIGUOUS",
"reason":"что именно означает значение в данном фрагменте"}}]}}]}}
Верните ровно одну запись для каждого candidate_id, без новых идентификаторов. MATCHED требует один
family_key. AMBIGUOUS/UNCLASSIFIED не должны угадывать family_key. Facility допустим только при
явной привязке из текста или контекста; нахождение в одном документе недостаточно.
Верните ровно одну quantity_reviews для каждого переданного quantity_candidate_id. WORK_QUANTITY
означает объём именно этой строительной операции. Размер, отметка, мощность, расход, процент,
продолжительность, цена и ресурс нормы не являются объёмом работы. Если табличная связь нарушена
или значение нельзя отнести без догадки, используйте AMBIGUOUS, а не WORK_QUANTITY.
deterministic_family_hint получен воспроизводимым словарём и может быть принят как family_key, если
контекст ему не противоречит; сооружение всё равно требует явной привязки.
"""


def _parse(
    raw: str,
    *,
    input_ids: tuple[str, ...],
    wording_by_id: Mapping[str, str],
    quantity_ids_by_work: Mapping[str, tuple[str, ...]],
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
        raw_quantity_reviews = value.get("quantity_reviews")
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
        if status == "NOT_A_WORK" and _POTENTIAL_WORK_AT_START.search(
            wording_by_id.get(candidate_id, "").strip()
        ):
            raise QwenSemanticFailure("qwen_work_reconciliation_potential_work_excluded")
        if facility is not None and facility not in allowed_facilities:
            raise QwenSemanticFailure("qwen_work_reconciliation_facility_invalid")
        if facility is not None and _WEAK_FACILITY_REASON.search(reason):
            facility = None
            reason = (
                f"{reason} Привязка к сооружению не принята: близость упоминаний без явной "
                "инженерной связи недостаточна."
            )
        quantity_ids = quantity_ids_by_work.get(candidate_id, ())
        quantity_reviews = _parse_quantity_reviews(raw_quantity_reviews, quantity_ids)
        observation: dict[str, Any] = {
            "candidate_id": candidate_id,
            "status": status,
            "family_key": family_key,
            "operation": operation,
            "facility": facility,
            "confidence": format(confidence, "f"),
            "reason": reason[:500],
        }
        if quantity_ids:
            observation["quantity_reviews"] = quantity_reviews
        observations[candidate_id] = observation
    if set(observations) != allowed_ids:
        raise QwenSemanticFailure("qwen_work_reconciliation_incomplete_output")
    return [observations[candidate_id] for candidate_id in input_ids]


def _parse_quantity_reviews(raw: object, input_ids: tuple[str, ...]) -> list[dict[str, str]]:
    if not input_ids:
        if raw not in (None, []):
            raise QwenSemanticFailure("qwen_work_reconciliation_quantity_output_unexpected")
        return []
    if not isinstance(raw, list) or len(raw) != len(input_ids):
        raise QwenSemanticFailure("qwen_work_reconciliation_quantity_output_incomplete")
    allowed_ids = set(input_ids)
    reviews: dict[str, dict[str, str]] = {}
    for value in raw:
        if not isinstance(value, dict):
            raise QwenSemanticFailure("qwen_work_reconciliation_quantity_output_invalid")
        candidate_id = str(value.get("quantity_candidate_id") or "")
        status = str(value.get("status") or "")
        reason = " ".join(str(value.get("reason") or "").split())
        if (
            candidate_id not in allowed_ids
            or candidate_id in reviews
            or status not in _QUANTITY_STATUSES
            or not reason
        ):
            raise QwenSemanticFailure("qwen_work_reconciliation_quantity_output_invalid")
        reviews[candidate_id] = {
            "quantity_candidate_id": candidate_id,
            "status": status,
            "reason": reason[:500],
        }
    if set(reviews) != allowed_ids:
        raise QwenSemanticFailure("qwen_work_reconciliation_quantity_output_incomplete")
    return [reviews[candidate_id] for candidate_id in input_ids]
