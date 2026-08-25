from __future__ import annotations

import json

import pytest

from asd_kontur.ntd.acceptance import (
    NtdAcceptanceError,
    validate_gap_non_fabrication_response,
)


def _response() -> dict[str, object]:
    return {
        "task_id": "task",
        "disposition": "insufficient",
        "gateway_status": "knowledge_gap",
        "normative_requirement": None,
        "practice_recommendation": None,
        "workspace_fact": None,
        "deterministic_rule_version": None,
        "normative_document_id": None,
        "normative_edition_id": None,
        "practice_guide_edition_id": "guide-edition",
        "source_version_id": "source-version",
        "practice_guide_reference_ids": ["reference"],
        "citations": ["page:16:region:0.1,0.2,0.8,0.3"],
        "gap_code": "official_access_blocked",
        "applicability_status": "indeterminate",
        "authority_distinction": "The guide reference is not an official provision.",
        "limitations": ["Official edition is unavailable."],
    }


def _validate(value: str) -> dict[str, object]:
    return validate_gap_non_fabrication_response(
        value,
        task_id="task",
        practice_guide_edition_id="guide-edition",
        source_version_id="source-version",
        practice_guide_reference_ids=("reference",),
        citations=("page:16:region:0.1,0.2,0.8,0.3",),
    )


def test_accepts_exact_non_fabricating_gap_response() -> None:
    assert _validate(json.dumps(_response()))["disposition"] == "insufficient"


def test_rejects_malformed_or_authority_fabricating_response() -> None:
    with pytest.raises(NtdAcceptanceError, match="NOT_STRICT_JSON"):
        _validate("not json")
    value = _response()
    value["normative_requirement"] = "fabricated requirement"
    with pytest.raises(NtdAcceptanceError, match="FABRICATED_AUTHORITY"):
        _validate(json.dumps(value))
