"""Editable handover register for current, confirmed contract conditions."""

from __future__ import annotations

import csv
import io
from collections.abc import Iterable, Mapping
from typing import Any

_FIELDS = (
    "clause_key",
    "category",
    "responsible_party",
    "required_action",
    "condition",
    "source_document",
    "source_page",
    "source_version_id",
    "source_locator_id",
    "reviewed_at",
    "execution_status",
    "execution_evidence",
)


def render_contract_execution_conditions_csv(
    conditions: Iterable[Mapping[str, Any]],
) -> bytes:
    """Export only current human-confirmed, source-linked planning conditions.

    Empty execution columns are deliberate: extraction and review do not prove
    that an obligation has been performed or accepted on site.
    """

    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=_FIELDS)
    writer.writeheader()
    for item in conditions:
        if item.get("review_state") != "confirmed" or not item.get("source_locator_id"):
            continue
        values = {
            "clause_key": item.get("display_clause_ref") or item.get("clause_key"),
            "category": item.get("category"),
            "responsible_party": item.get("party"),
            "required_action": item.get("obligation"),
            "condition": item.get("condition"),
            "source_document": item.get("source_name"),
            "source_page": item.get("source_page"),
            "source_version_id": item.get("source_version_id"),
            "source_locator_id": item.get("source_locator_id"),
            "reviewed_at": item.get("reviewed_at"),
            "execution_status": "",
            "execution_evidence": "",
        }
        writer.writerow({field: _safe_cell(values[field]) for field in _FIELDS})
    return ("\ufeff" + output.getvalue()).encode("utf-8")


def _safe_cell(value: Any) -> str:
    text = "" if value is None else str(value)
    return "'" + text if text.startswith(("=", "+", "-", "@")) else text
