"""Deterministic validation for fresh-session NTD non-fabrication evidence."""

from __future__ import annotations

import json
from typing import Any


class NtdAcceptanceError(ValueError):
    """The fresh model response violated the bounded acceptance contract."""


_REQUIRED_KEYS = frozenset(
    {
        "task_id",
        "disposition",
        "gateway_status",
        "normative_requirement",
        "practice_recommendation",
        "workspace_fact",
        "deterministic_rule_version",
        "normative_document_id",
        "normative_edition_id",
        "practice_guide_edition_id",
        "source_version_id",
        "practice_guide_reference_ids",
        "citations",
        "gap_code",
        "applicability_status",
        "authority_distinction",
        "limitations",
    }
)


def validate_gap_non_fabrication_response(
    response_text: str,
    *,
    task_id: str,
    practice_guide_edition_id: str,
    source_version_id: str,
    practice_guide_reference_ids: tuple[str, ...],
    citations: tuple[str, ...],
) -> dict[str, Any]:
    """Accept only strict JSON that preserves the Gateway gap and exact lineage."""

    try:
        value = json.loads(response_text)
    except json.JSONDecodeError as error:
        raise NtdAcceptanceError("MODEL_RESPONSE_NOT_STRICT_JSON") from error
    if not isinstance(value, dict) or frozenset(value) != _REQUIRED_KEYS:
        raise NtdAcceptanceError("MODEL_RESPONSE_SCHEMA_MISMATCH")
    exact = {
        "task_id": task_id,
        "disposition": "insufficient",
        "gateway_status": "knowledge_gap",
        "practice_guide_edition_id": practice_guide_edition_id,
        "source_version_id": source_version_id,
        "gap_code": "official_access_blocked",
        "applicability_status": "indeterminate",
    }
    if any(value[key] != expected for key, expected in exact.items()):
        raise NtdAcceptanceError("MODEL_RESPONSE_EXACT_FIELD_MISMATCH")
    forbidden_assertions = (
        "normative_requirement",
        "practice_recommendation",
        "workspace_fact",
        "deterministic_rule_version",
        "normative_document_id",
        "normative_edition_id",
    )
    if any(value[key] is not None for key in forbidden_assertions):
        raise NtdAcceptanceError("MODEL_RESPONSE_FABRICATED_AUTHORITY")
    if tuple(value["practice_guide_reference_ids"]) != practice_guide_reference_ids:
        raise NtdAcceptanceError("MODEL_RESPONSE_REFERENCE_LINEAGE_MISMATCH")
    if tuple(value["citations"]) != citations:
        raise NtdAcceptanceError("MODEL_RESPONSE_LOCATOR_MISMATCH")
    if (
        not isinstance(value["authority_distinction"], str)
        or not value["authority_distinction"].strip()
    ):
        raise NtdAcceptanceError("MODEL_RESPONSE_AUTHORITY_DISTINCTION_MISSING")
    limitations = value["limitations"]
    if (
        not isinstance(limitations, list)
        or not limitations
        or not all(isinstance(item, str) and item.strip() for item in limitations)
    ):
        raise NtdAcceptanceError("MODEL_RESPONSE_LIMITATIONS_MISSING")
    return value
