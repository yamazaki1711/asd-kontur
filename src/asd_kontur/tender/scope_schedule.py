"""Editable source-scoped Tender work schedule rendering.

This is a candidate projection of the shared project model.  It deliberately
does not aggregate same-named work, quantities, or materials across source
scopes: a commercial total requires a separately evidenced reconciliation.
"""

from __future__ import annotations

import csv
import io
from collections.abc import Iterable, Mapping
from typing import Any

from .findings_schedule import source_reference


def render_tender_scope_schedule_csv(
    work_packages: Iterable[Mapping[str, Any]],
    *,
    materialization_state: str,
    coverage_gaps: Iterable[str],
    evidence_index: Mapping[str, Mapping[str, Any]] | None = None,
) -> bytes:
    """Render one evidence-bound schedule row for every candidate work scope."""

    output = io.StringIO(newline="")
    writer = csv.DictWriter(
        output,
        fieldnames=(
            "work_package_id",
            "work_name",
            "normalized_work_name",
            "scope",
            "candidate_observation_count",
            "quantity_observations",
            "material_observations",
            "source_references",
            "source_locator_ids",
            "uncertainties",
            "candidate_status",
            "materialization_state",
            "coverage_gaps",
        ),
    )
    writer.writeheader()
    evidence = evidence_index or {}
    gaps = ";".join(sorted(str(item) for item in coverage_gaps))
    rows = [_scope_row(item, evidence) for item in work_packages]
    for row in sorted(
        rows,
        key=lambda item: (item["normalized_work_name"], item["scope"], item["work_package_id"]),
    ):
        writer.writerow(
            {
                **row,
                "materialization_state": materialization_state,
                "coverage_gaps": gaps,
            }
        )
    return ("\ufeff" + output.getvalue()).encode("utf-8")


def _scope_row(
    item: Mapping[str, Any], evidence_index: Mapping[str, Mapping[str, Any]]
) -> dict[str, str]:
    package = item.get("package")
    package = package if isinstance(package, Mapping) else {}
    work_type = package.get("work_type")
    work_type = work_type if isinstance(work_type, Mapping) else {}
    locator_ids = tuple(str(value) for value in package.get("source_locator_ids") or ())
    return {
        "work_package_id": str(item.get("work_package_id") or package.get("work_package_id") or ""),
        "work_name": str(work_type.get("raw") or work_type.get("normalized") or ""),
        "normalized_work_name": str(work_type.get("normalized") or ""),
        "scope": str(package.get("scope") or "scope_not_specified"),
        "candidate_observation_count": str(package.get("candidate_observation_count") or 0),
        "quantity_observations": " | ".join(
            _quantity_text(value)
            for value in package.get("quantities") or ()
            if isinstance(value, Mapping)
        ),
        "material_observations": " | ".join(
            _material_text(value)
            for value in package.get("materials") or ()
            if isinstance(value, Mapping)
        ),
        "source_references": "; ".join(
            source_reference(locator_id, evidence_index.get(locator_id))
            for locator_id in locator_ids
        ),
        "source_locator_ids": ";".join(locator_ids),
        "uncertainties": ";".join(
            sorted(str(value) for value in package.get("uncertainties") or ())
        ),
        "candidate_status": "candidate",
    }


def _quantity_text(value: Mapping[str, Any]) -> str:
    raw_value = str(value.get("raw_value") or "")
    raw_unit = str(value.get("raw_unit") or "")
    normalized_value = value.get("normalized_value")
    normalized_unit = value.get("normalized_unit")
    locator = str(value.get("source_locator_id") or "")
    normalized = (
        f"; normalized={normalized_value} {normalized_unit}"
        if normalized_value is not None and normalized_unit is not None
        else ""
    )
    return f"{raw_value} {raw_unit}{normalized}; locator={locator}".strip()


def _material_text(value: Mapping[str, Any]) -> str:
    name = str(value.get("raw_name") or "")
    quantity = str(value.get("raw_quantity") or "")
    unit = str(value.get("raw_unit") or "")
    locator = str(value.get("source_locator_id") or "")
    return f"{name}; {quantity} {unit}; locator={locator}".strip()
