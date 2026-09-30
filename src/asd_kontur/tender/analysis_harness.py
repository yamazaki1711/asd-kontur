"""Project-independent task contracts for local-Qwen Tender analysis.

The harness describes how to ask bounded construction questions. It never
contains a project name, expected quantity, facility, or expected finding.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class TenderAnalysisTask(StrEnum):
    DOCUMENT_ROLE_CLASSIFICATION = "DOCUMENT_ROLE_CLASSIFICATION"
    PROJECT_SUMMARY_EXTRACTION = "PROJECT_SUMMARY_EXTRACTION"
    PROJECT_PARTICIPANT_EXTRACTION = "PROJECT_PARTICIPANT_EXTRACTION"
    PROJECT_ENTITY_EXTRACTION = "PROJECT_ENTITY_EXTRACTION"
    FACILITY_STRUCTURE_EXTRACTION = "FACILITY_STRUCTURE_EXTRACTION"
    STRUCTURE_RELATIONSHIP_RESOLUTION = "STRUCTURE_RELATIONSHIP_RESOLUTION"
    WORK_CLASSIFICATION = "WORK_CLASSIFICATION"
    WORK_SCOPE_RESOLUTION = "WORK_SCOPE_RESOLUTION"
    QUANTITY_SCOPE_INTERPRETATION = "QUANTITY_SCOPE_INTERPRETATION"
    QUANTITY_RELATIONSHIP_ANALYSIS = "QUANTITY_RELATIONSHIP_ANALYSIS"
    MATERIAL_SCOPE_INTERPRETATION = "MATERIAL_SCOPE_INTERPRETATION"
    MATERIAL_RELATIONSHIP_ANALYSIS = "MATERIAL_RELATIONSHIP_ANALYSIS"
    STRUCTURE_IDENTITY_RESOLUTION = "STRUCTURE_IDENTITY_RESOLUTION"
    DOCUMENT_SCOPE_MATCHING = "DOCUMENT_SCOPE_MATCHING"
    CROSS_DOCUMENT_SCOPE_MATCHING = "CROSS_DOCUMENT_SCOPE_MATCHING"
    ENGINEERING_CONTRADICTION_REVIEW = "ENGINEERING_CONTRADICTION_REVIEW"
    COMMERCIAL_COMPLETENESS_REVIEW = "COMMERCIAL_COMPLETENESS_REVIEW"
    COMMERCIAL_SCOPE_MATCHING = "COMMERCIAL_SCOPE_MATCHING"
    PROCUREMENT_SUMMARY = "PROCUREMENT_SUMMARY"
    CONTRACT_SUMMARY = "CONTRACT_SUMMARY"
    CONTRACT_RISK_REVIEW = "CONTRACT_RISK_REVIEW"
    CUSTOMER_QUESTION_GENERATION = "CUSTOMER_QUESTION_GENERATION"
    CONTRACTOR_RISK_GENERATION = "CONTRACTOR_RISK_GENERATION"
    NTD_APPLICABILITY_REVIEW = "NTD_APPLICABILITY_REVIEW"


class TenderHarnessDecision(StrEnum):
    ESTABLISHED = "ESTABLISHED"
    PROBABLE = "PROBABLE"
    DISTINCT = "DISTINCT"
    AMBIGUOUS = "AMBIGUOUS"
    CONFLICTING = "CONFLICTING"
    NOT_APPLICABLE = "NOT_APPLICABLE"


_CONFIDENCE_VALUES = frozenset({"HIGH", "MODERATE", "LOW"})


@dataclass(frozen=True, slots=True)
class TenderHarnessTaskInput:
    task: TenderAnalysisTask
    input_identity: str
    context: dict[str, Any]

    def __post_init__(self) -> None:
        if not self.input_identity.strip():
            raise ValueError("tender harness input identity is required")


def bounded_task_payload(
    task: TenderHarnessTaskInput,
    *,
    max_chars: int = 12_000,
) -> str:
    """Serialize one exact task without silently truncating structured input."""

    if not 1_000 <= max_chars <= 50_000:
        raise ValueError("tender harness context bound is invalid")
    payload = json.dumps(
        {
            "task": task.task.value,
            "input_identity": task.input_identity,
            "context": task.context,
        },
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
        default=str,
    )
    if len(payload) > max_chars:
        raise ValueError("tender harness context exceeds the declared bound")
    return payload


def validate_task_result(
    task: TenderHarnessTaskInput,
    value: dict[str, Any],
) -> dict[str, Any]:
    """Validate the shared envelope used by every project-independent task.

    Task-specific parsers may impose stricter fields, but no core semantic
    result may omit its input identity, decision, uncertainty, or sources.
    """

    if value.get("input_identity") != task.input_identity:
        raise ValueError("tender harness result input identity mismatch")
    try:
        decision = TenderHarnessDecision(str(value.get("decision") or ""))
    except ValueError as exc:
        raise ValueError("tender harness result decision is invalid") from exc
    confidence = str(value.get("confidence") or "")
    if confidence not in _CONFIDENCE_VALUES:
        raise ValueError("tender harness result confidence is invalid")
    source_references = value.get("source_references")
    if not isinstance(source_references, list) or not all(
        isinstance(item, str) and item.strip() for item in source_references
    ):
        raise ValueError("tender harness result source references are invalid")
    ambiguity = value.get("ambiguity")
    if decision in {
        TenderHarnessDecision.AMBIGUOUS,
        TenderHarnessDecision.CONFLICTING,
    } and not (isinstance(ambiguity, str) and ambiguity.strip()):
        raise ValueError("tender harness ambiguous result requires an explanation")
    normalized = value.get("normalized_interpretation")
    if (
        decision
        not in {
            TenderHarnessDecision.AMBIGUOUS,
            TenderHarnessDecision.NOT_APPLICABLE,
        }
        and normalized is None
    ):
        raise ValueError("tender harness result requires normalized interpretation")
    return {
        "task": task.task.value,
        "input_identity": task.input_identity,
        "decision": decision.value,
        "normalized_interpretation": normalized,
        "relationships": list(value.get("relationships") or ()),
        "confidence": confidence,
        "ambiguity": ambiguity,
        "source_references": source_references,
    }
