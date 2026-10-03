"""Editable export for the non-authoritative Audit package preflight."""

from __future__ import annotations

import csv
import io
from collections.abc import Iterable, Mapping
from typing import Any


def render_expected_actual_preflight_csv(preflight: Mapping[str, Any]) -> bytes:
    """Render the exact preflight projection without changing its authority.

    The row key contains work-package and immutable requirement identity, so a
    spreadsheet user cannot mistake same-named forms for a single obligation.
    This is an editable working schedule, not an audit conclusion or a
    substitute for source-document inspection.
    """

    output = io.StringIO(newline="")
    writer = csv.DictWriter(
        output,
        fieldnames=(
            "item_key",
            "work_package_id",
            "document_requirement_id",
            "document_requirement_version",
            "document_type",
            "required_stage",
            "requirement_state",
            "authority_status",
            "expected_copies",
            "preflight_state",
            "membership_count",
            "membership_states",
            "evidence_refs",
            "gaps",
            "required_correction",
            "practical_consequence",
            "audit_boundary",
        ),
    )
    writer.writeheader()
    for item in _items(preflight.get("items", ())):
        writer.writerow(
            {
                "item_key": str(item.get("item_key", "")),
                "work_package_id": str(item.get("work_package_id", "")),
                "document_requirement_id": str(item.get("document_requirement_id", "")),
                "document_requirement_version": str(item.get("document_requirement_version", "")),
                "document_type": str(item.get("document_type", "")),
                "required_stage": str(item.get("required_stage", "")),
                "requirement_state": str(item.get("requirement_state", "")),
                "authority_status": str(item.get("authority_status", "")),
                "expected_copies": str(item.get("expected_copies", "")),
                "preflight_state": str(item.get("preflight_state", "")),
                "membership_count": str(item.get("membership_count", "")),
                "membership_states": ";".join(
                    str(value) for value in item.get("membership_states", ())
                ),
                "evidence_refs": ";".join(str(value) for value in item.get("evidence_refs", ())),
                "gaps": ";".join(str(value) for value in item.get("gaps", ())),
                "required_correction": str(item.get("required_correction", "")),
                "practical_consequence": str(item.get("practical_consequence", "")),
                "audit_boundary": str(item.get("audit_boundary", "")),
            }
        )
    return ("\ufeff" + output.getvalue()).encode("utf-8")


def _items(values: Iterable[object]) -> Iterable[Mapping[str, Any]]:
    return (value for value in values if isinstance(value, Mapping))
