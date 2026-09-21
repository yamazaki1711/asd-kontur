"""Editable Tender document-coverage schedule.

The schedule is a delivery projection of workspace processing state.  It does
not turn an admitted document, an OCR result, or a successful batch into a
claim that its engineering content was reconciled.
"""

from __future__ import annotations

import csv
import io
from collections.abc import Iterable, Mapping
from typing import Any


def render_tender_document_coverage_csv(
    coverage: Iterable[Mapping[str, Any]],
    *,
    materialization_state: str,
    coverage_gaps: Iterable[str],
) -> bytes:
    """Render one truthful coverage row for every active source version."""

    output = io.StringIO(newline="")
    writer = csv.DictWriter(
        output,
        fieldnames=(
            "document_name",
            "document_version",
            "source_version_id",
            "admission_status",
            "native_extraction_status",
            "page_count",
            "semantic_profile_version",
            "expected_fragment_count",
            "accepted_batch_count",
            "accepted_fragment_count",
            "covered_fragment_count",
            "unresolved_fragment_count",
            "failed_batch_count",
            "failed_fragment_count",
            "recovered_failed_fragment_count",
            "unresolved_failed_fragment_count",
            "semantic_coverage_state",
            "project_materialization_state",
            "project_coverage_gaps",
        ),
    )
    writer.writeheader()
    gaps = ";".join(sorted(str(item) for item in coverage_gaps))
    rows = sorted(
        (dict(item) for item in coverage),
        key=lambda item: (
            str(item.get("safe_display_name") or ""),
            str(item.get("source_version_id") or ""),
        ),
    )
    for row in rows:
        writer.writerow(
            {
                "document_name": _text(row.get("safe_display_name")),
                "document_version": _text(row.get("document_version")),
                "source_version_id": _text(row.get("source_version_id")),
                "admission_status": _text(row.get("admission_status")),
                "native_extraction_status": _text(row.get("extraction_status")),
                "page_count": _text(row.get("page_count")),
                "semantic_profile_version": _text(row.get("profile_version")),
                "expected_fragment_count": _text(row.get("expected_fragment_count")),
                "accepted_batch_count": _text(row.get("accepted_batch_count")),
                "accepted_fragment_count": _text(row.get("accepted_fragment_count")),
                "covered_fragment_count": _text(row.get("covered_fragment_count")),
                "unresolved_fragment_count": _text(row.get("unresolved_fragment_count")),
                "failed_batch_count": _text(row.get("failed_batch_count")),
                "failed_fragment_count": _text(row.get("failed_fragment_count")),
                "recovered_failed_fragment_count": _text(
                    row.get("recovered_failed_fragment_count")
                ),
                "unresolved_failed_fragment_count": _text(
                    row.get("unresolved_failed_fragment_count")
                ),
                "semantic_coverage_state": _text(row.get("state")),
                "project_materialization_state": materialization_state,
                "project_coverage_gaps": gaps,
            }
        )
    return ("\ufeff" + output.getvalue()).encode("utf-8")


def _text(value: object | None) -> str:
    return "" if value is None else str(value)
