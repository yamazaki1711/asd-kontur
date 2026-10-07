"""Editable, non-authoritative inventory of admitted workspace documents."""

from __future__ import annotations

import csv
import io
from collections.abc import Iterable, Mapping
from typing import Any

_FIELDS = (
    "document_id",
    "version",
    "source_version_id",
    "safe_display_name",
    "source_kind",
    "preliminary_document_roles",
    "page_count",
    "admission_status",
    "extraction_status",
    "independent_content_review",
    "document_identity_review",
    "revision_review",
    "signature_review",
    "work_quantity_review",
    "reviewer_note",
)


def render_uploaded_document_inventory_csv(documents: Iterable[Mapping[str, Any]]) -> bytes:
    """Export every active version without converting a role into an Audit verdict.

    The blank review columns are intentionally editable human working fields;
    they do not become application Facts or a canonical Audit conclusion.
    """

    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=_FIELDS)
    writer.writeheader()
    for document in documents:
        row = {
            "document_id": str(document["document_id"]),
            "version": str(document["version"]),
            "source_version_id": str(document.get("source_version_id") or ""),
            "safe_display_name": str(document.get("safe_display_name") or ""),
            "source_kind": str(document.get("source_kind") or ""),
            "preliminary_document_roles": "; ".join(document.get("document_roles") or ()),
            "page_count": str(document.get("page_count") or ""),
            "admission_status": str(document.get("admission_status") or ""),
            "extraction_status": str(document.get("extraction_status") or ""),
            "independent_content_review": "not_performed",
            "document_identity_review": "",
            "revision_review": "",
            "signature_review": "",
            "work_quantity_review": "",
            "reviewer_note": "",
        }
        writer.writerow({key: _safe_cell(value) for key, value in row.items()})
    return ("\ufeff" + output.getvalue()).encode("utf-8")


def _safe_cell(value: str) -> str:
    """Do not execute an uploaded filename/role as a spreadsheet formula."""

    return "'" + value if value.lstrip().startswith(("=", "+", "-", "@")) else value
