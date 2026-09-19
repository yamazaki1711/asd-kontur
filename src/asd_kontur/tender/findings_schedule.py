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
    evidence_index: Mapping[str, Mapping[str, Any]] | None = None,
    work_packages: Iterable[Mapping[str, Any]] = (),
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
            "work_package_id",
            "work_name",
            "scope",
            "work_relation",
            "required_input",
            "practical_consequence",
            "source_references",
            "source_locator_ids",
            "parameters_json",
            "materialization_state",
            "coverage_gaps",
        ),
    )
    writer.writeheader()
    gap_value = ";".join(sorted(str(item) for item in coverage_gaps))
    packages_by_observation = _work_packages_by_observation(work_packages)
    for defect in sorted(defects, key=lambda item: (str(item.get("defect_id", "")), str(item))):
        kind = str(defect.get("defect_kind", "unknown"))
        state, required_input, consequence = finding_presentation(kind)
        parameters = defect.get("parameters")
        if isinstance(parameters, Mapping):
            required_input = str(parameters.get("missing_input") or required_input)
            consequence = str(parameters.get("consequence") or consequence)
        else:
            parameters = {}
        locator_ids = tuple(str(item) for item in defect.get("source_locator_ids", []))
        work_context = finding_work_context(defect, packages_by_observation)
        resolved_evidence = evidence_index or {}
        writer.writerow(
            {
                "finding_id": str(defect.get("defect_id", "")),
                "kind": kind,
                "assessment_state": state,
                "subject_identity": str(defect.get("subject_identity", "")),
                "related_identity": str(defect.get("related_identity") or ""),
                "work_package_id": work_context["work_package_id"],
                "work_name": work_context["work_name"],
                "scope": work_context["scope"],
                "work_relation": work_context["work_relation"],
                "required_input": required_input,
                "practical_consequence": consequence,
                "source_references": ";".join(
                    source_reference(locator_id, resolved_evidence.get(locator_id))
                    for locator_id in locator_ids
                ),
                "source_locator_ids": ";".join(locator_ids),
                "parameters_json": json.dumps(parameters, ensure_ascii=False, sort_keys=True),
                "materialization_state": materialization_state,
                "coverage_gaps": gap_value,
            }
        )
    return ("\ufeff" + output.getvalue()).encode("utf-8")


def finding_work_context(
    defect: Mapping[str, Any],
    packages_by_observation: Mapping[str, Mapping[str, str]],
) -> dict[str, str]:
    """Resolve a finding to a source-scoped work package by exact candidate ID.

    A finding can point to a work candidate or to a related estimate/quantity.
    Only an exact candidate-observation membership is sufficient to present a
    work context; labels must never merge identical work names across scopes.
    """

    for relation, identity in (
        ("subject", defect.get("subject_identity")),
        ("related", defect.get("related_identity")),
    ):
        candidate = packages_by_observation.get(str(identity or ""))
        if candidate is not None:
            return {**candidate, "work_relation": relation}
    return {
        "work_package_id": "",
        "work_name": "",
        "scope": "",
        "work_relation": "not_resolved",
    }


def _work_packages_by_observation(
    work_packages: Iterable[Mapping[str, Any]],
) -> dict[str, dict[str, str]]:
    """Build only unambiguous exact memberships for user-facing exports."""

    matches: dict[str, list[dict[str, str]]] = {}
    for item in work_packages:
        package = item.get("package")
        if not isinstance(package, Mapping):
            continue
        work_type = package.get("work_type")
        work_type = work_type if isinstance(work_type, Mapping) else {}
        context = {
            "work_package_id": str(
                item.get("work_package_id") or package.get("work_package_id") or ""
            ),
            "work_name": str(work_type.get("raw") or work_type.get("normalized") or ""),
            "scope": str(package.get("scope") or "scope_not_specified"),
        }
        for observation_id in package.get("candidate_observation_ids") or ():
            matches.setdefault(str(observation_id), []).append(context)
    return {
        observation_id: contexts[0]
        for observation_id, contexts in matches.items()
        if len(contexts) == 1
    }


def finding_presentation(kind: str) -> tuple[str, str, str]:
    """Return a stable candidate-state explanation for a finding kind."""

    return _PRESENTATION.get(
        kind,
        (
            "candidate_requires_engineering_review",
            "engineering review of the exact source evidence",
            "the observation is not a confirmed Tender conclusion",
        ),
    )


def source_reference(locator_id: str, evidence: Mapping[str, Any] | None) -> str:
    """Provide a human-readable evidence pointer without replacing its identity.

    CSV consumers need a document/revision/page reference.  The stable locator
    ID remains in the adjacent audit column, so this presentation projection
    cannot silently redirect a finding to another source.
    """

    if evidence is None:
        return f"unresolved locator ({locator_id})"
    document = str(evidence.get("safe_display_name") or "source document")
    version = evidence.get("document_version")
    locator = str(evidence.get("locator_value") or evidence.get("locator_kind") or "location")
    version_suffix = f", version {version}" if version is not None else ""
    return f"{document}{version_suffix}, {locator} ({locator_id})"
