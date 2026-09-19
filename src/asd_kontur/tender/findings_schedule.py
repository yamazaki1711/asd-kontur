"""Editable, evidence-bound Tender findings schedule rendering."""

from __future__ import annotations

import csv
import io
import json
from collections.abc import Iterable, Mapping
from typing import Any

_PRESENTATION: dict[str, tuple[str, str, str]] = {
    "estimate_comparison_input_unavailable": (
        "comparison_not_performed",
        "parsed estimate or bill-of-quantities positions",
        "work omissions and quantity deltas cannot be evaluated",
    ),
    "project_work_missing_in_estimate": (
        "candidate_difference",
        "engineering comparison of the linked project work and estimate position",
        "scope or pricing clarification is required before bid submission",
    ),
    "quantity_mismatch": (
        "candidate_difference",
        "reconciled source quantities and units",
        "quantity basis requires clarification before pricing",
    ),
    "project_material_missing_in_estimate": (
        "candidate_difference",
        "engineering comparison of project material and estimate position",
        "material scope or pricing clarification is required",
    ),
    "estimate_position_unsupported_by_project": (
        "candidate_difference",
        "project source supporting the estimate position",
        "estimate scope requires clarification",
    ),
    "incompatible_units": (
        "candidate_difference",
        "unit conversion basis or corrected source unit",
        "quantities cannot be compared reproducibly",
    ),
    "ambiguous_source_match": (
        "ambiguous",
        "scope or identity evidence for the linked observations",
        "the system deliberately does not attach or total the observations",
    ),
}


def render_tender_findings_csv(
    defects: Iterable[Mapping[str, Any]],
    *,
    materialization_state: str,
    coverage_gaps: Iterable[str],
) -> bytes:
    """Render a UTF-8 BOM CSV intended for editing in ordinary office tools.

    The export is a candidate schedule.  It never changes the status of a
    reconciliation observation and exposes why a comparison was not performed.
    """

    output = io.StringIO(newline="")
    writer = csv.DictWriter(
        output,
        fieldnames=(
            "finding_id",
            "kind",
            "assessment_state",
            "subject_identity",
            "related_identity",
            "required_input",
            "practical_consequence",
            "source_locator_ids",
            "parameters_json",
            "materialization_state",
            "coverage_gaps",
        ),
    )
    writer.writeheader()
    gap_value = ";".join(sorted(str(item) for item in coverage_gaps))
    for defect in sorted(defects, key=lambda item: (str(item.get("defect_id", "")), str(item))):
        kind = str(defect.get("defect_kind", "unknown"))
        state, required_input, consequence = _PRESENTATION.get(
            kind,
            (
                "candidate_requires_engineering_review",
                "engineering review of the exact source evidence",
                "the observation is not a confirmed Tender conclusion",
            ),
        )
        parameters = defect.get("parameters")
        if isinstance(parameters, Mapping):
            required_input = str(parameters.get("missing_input") or required_input)
            consequence = str(parameters.get("consequence") or consequence)
        else:
            parameters = {}
        writer.writerow(
            {
                "finding_id": str(defect.get("defect_id", "")),
                "kind": kind,
                "assessment_state": state,
                "subject_identity": str(defect.get("subject_identity", "")),
                "related_identity": str(defect.get("related_identity") or ""),
                "required_input": required_input,
                "practical_consequence": consequence,
                "source_locator_ids": ";".join(
                    str(item) for item in defect.get("source_locator_ids", [])
                ),
                "parameters_json": json.dumps(parameters, ensure_ascii=False, sort_keys=True),
                "materialization_state": materialization_state,
                "coverage_gaps": gap_value,
            }
        )
    return ("\ufeff" + output.getvalue()).encode("utf-8")
