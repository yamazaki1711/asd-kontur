"""Deterministic Tender analysis export built from current candidate projections."""

from __future__ import annotations

import hashlib
import io
import json
import zipfile
from collections.abc import Mapping
from typing import Any

_FIXED_ZIP_TIME = (1980, 1, 1, 0, 0, 0)


def build_tender_analysis_archive(
    *,
    findings_report: bytes,
    findings_schedule: bytes,
    scope_schedule: bytes,
    structure_identity_schedule: bytes,
    facility_scope_schedule: bytes,
    facility_candidate_schedule: bytes,
    document_coverage_schedule: bytes,
    materialization: Mapping[str, Any],
    professional: bool = False,
    material_schedule: bytes | None = None,
    disagreement_protocol: bytes | None = None,
    revised_contract: bytes | None = None,
) -> bytes:
    """Return a stable editable Tender deliverable without changing findings.

    The archive does not create a contract conclusion or a project-wide total.
    Its status file makes incomplete coverage explicit beside the editable
    candidate projections.
    """

    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        professional_entries: tuple[tuple[str, bytes], ...] = ()
        if professional and disagreement_protocol:
            professional_entries += (
                ("04_disagreement_protocol_candidate.docx", disagreement_protocol),
            )
        if professional and revised_contract:
            professional_entries += (("05_revised_contract_candidate.docx", revised_contract),)
        professional_offset = 1 if professional and revised_contract else 0
        entries = (
            (
                "01_tender_engineering_report.docx"
                if professional
                else "01_tender_findings_report.docx",
                findings_report,
            ),
            (
                "02_engineering_findings_and_actions.csv"
                if professional
                else "02_tender_findings_schedule.csv",
                findings_schedule,
            ),
            (
                "03_project_work_quantity_material_schedule.csv"
                if professional
                else "03_tender_work_resource_schedule.csv",
                scope_schedule,
            ),
            *professional_entries,
            (
                f"{5 + professional_offset:02d}_structure_identity_candidates.csv"
                if professional
                else "04_structure_identity_candidates.csv",
                structure_identity_schedule,
            ),
            (
                f"{6 + professional_offset:02d}_facility_work_observation_candidates.csv"
                if professional
                else "05_facility_work_observation_candidates.csv",
                facility_scope_schedule,
            ),
            (
                f"{7 + professional_offset:02d}_facility_work_candidate_groups.csv"
                if professional
                else "06_facility_work_candidate_groups.csv",
                facility_candidate_schedule,
            ),
            (
                f"{8 + professional_offset:02d}_document_processing_coverage.csv"
                if professional
                else "07_document_processing_coverage.csv",
                document_coverage_schedule,
            ),
            *(
                (("20_project_material_observations.csv", material_schedule),)
                if professional and material_schedule is not None
                else ()
            ),
        )
        manifest = _delivery_manifest(entries, materialization)
        for name, payload in (
            *entries,
            (
                (
                    f"{9 + professional_offset:02d}_delivery_manifest.json"
                    if professional
                    else "08_delivery_manifest.json"
                ),
                manifest,
            ),
            ("99_analysis_status.txt", _status_text(materialization, professional=professional)),
        ):
            info = zipfile.ZipInfo(name, _FIXED_ZIP_TIME)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o600 << 16
            archive.writestr(info, payload)
    return output.getvalue()


def _delivery_manifest(
    entries: tuple[tuple[str, bytes], ...], materialization: Mapping[str, Any]
) -> bytes:
    """Bind this download to exact candidate projections and coverage state."""

    payload = {
        "contract": "tender.analysis-delivery@1.6.0",
        "candidate_boundary": True,
        "materialization": {
            "state": str(materialization.get("state") or "not_requested"),
            "reconciliation_id": materialization.get("reconciliation_id"),
            "run_id": materialization.get("run_id"),
            "run_version": materialization.get("run_version"),
            "coverage_gaps": sorted(str(value) for value in materialization.get("gaps") or ()),
        },
        "entries": [
            {
                "path": name,
                "sha256": "sha256:" + hashlib.sha256(content).hexdigest(),
                "size_bytes": len(content),
            }
            for name, content in entries
        ],
    }
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )


def _status_text(materialization: Mapping[str, Any], *, professional: bool = False) -> bytes:
    state = str(materialization.get("state") or "not_requested")
    gaps = sorted(str(value) for value in materialization.get("gaps") or ())
    if professional:
        lines = [
            "Tender engineering analysis",
            f"Project-model materialization state: {state}",
            "The report presents construction entities, work scopes, quantities, materials, "
            "comparisons, issues, risks and actions currently established by the project model.",
            "Incomplete or ambiguous source information remains explicitly marked in the report.",
            "Coverage gaps: " + ("; ".join(gaps) if gaps else "none recorded"),
        ]
        return ("\n".join(lines) + "\n").encode("utf-8")
    lines = [
        "Tender analysis candidate export",
        f"Project-model materialization state: {state}",
        "The included findings and schedules are source-bound candidates, not confirmed "
        "omissions, quantities, or contract conclusions.",
        "Same-named work in distinct source scopes is intentionally not aggregated.",
        "Cross-document structure identity rows are candidates and are not automatically merged.",
        "Facility/work associations require an exact shared source locator; "
        "ambiguous associations are retained.",
        "The document coverage schedule distinguishes native extraction from accepted "
        "semantic coverage.",
        "Coverage gaps: " + ("; ".join(gaps) if gaps else "none recorded"),
    ]
    return ("\n".join(lines) + "\n").encode("utf-8")
