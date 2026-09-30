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
    PROJECT_ENTITY_EXTRACTION = "PROJECT_ENTITY_EXTRACTION"
    WORK_CLASSIFICATION = "WORK_CLASSIFICATION"
    QUANTITY_SCOPE_INTERPRETATION = "QUANTITY_SCOPE_INTERPRETATION"
    QUANTITY_RELATIONSHIP_ANALYSIS = "QUANTITY_RELATIONSHIP_ANALYSIS"
    MATERIAL_RELATIONSHIP_ANALYSIS = "MATERIAL_RELATIONSHIP_ANALYSIS"
    STRUCTURE_IDENTITY_RESOLUTION = "STRUCTURE_IDENTITY_RESOLUTION"
    DOCUMENT_SCOPE_MATCHING = "DOCUMENT_SCOPE_MATCHING"
    ENGINEERING_CONTRADICTION_REVIEW = "ENGINEERING_CONTRADICTION_REVIEW"
    COMMERCIAL_COMPLETENESS_REVIEW = "COMMERCIAL_COMPLETENESS_REVIEW"
    PROCUREMENT_SUMMARY = "PROCUREMENT_SUMMARY"
    CONTRACT_RISK_REVIEW = "CONTRACT_RISK_REVIEW"
    NTD_APPLICABILITY_REVIEW = "NTD_APPLICABILITY_REVIEW"


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
