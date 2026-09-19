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
    materialization: Mapping[str, Any],
) -> bytes:
    """Return a stable editable Tender deliverable without changing findings.

    The archive does not create a contract conclusion or a project-wide total.
    Its status file makes incomplete coverage explicit beside the editable
    candidate projections.
    """

    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        entries = (
            ("01_tender_findings_report.docx", findings_report),
            ("02_tender_findings_schedule.csv", findings_schedule),
            ("03_tender_work_resource_schedule.csv", scope_schedule),
        )
        manifest = _delivery_manifest(entries, materialization)
        for name, payload in (
            *entries,
            ("04_delivery_manifest.json", manifest),
            ("99_analysis_status.txt", _status_text(materialization)),
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
        "contract": "tender.analysis-delivery@1.0.0",
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


def _status_text(materialization: Mapping[str, Any]) -> bytes:
    state = str(materialization.get("state") or "not_requested")
    gaps = sorted(str(value) for value in materialization.get("gaps") or ())
    lines = [
        "Tender analysis candidate export",
        f"Project-model materialization state: {state}",
        "The included findings and schedules are source-bound candidates, not confirmed "
        "omissions, quantities, or contract conclusions.",
        "Same-named work in distinct source scopes is intentionally not aggregated.",
        "Coverage gaps: " + ("; ".join(gaps) if gaps else "none recorded"),
    ]
    return ("\n".join(lines) + "\n").encode("utf-8")
