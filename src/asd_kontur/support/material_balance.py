"""Deterministic, non-stock-taking balance of recorded delivery and use."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from decimal import Decimal
from typing import Any


def calculate_material_balance(
    *,
    batch_version: int,
    version_count: int,
    admissions: Sequence[Mapping[str, Any]],
    applications: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Count one delivery basis per batch, never once per admitted work.

    A changed batch version or incompatible units has no defensible remaining
    quantity without a reconciliation of the physical stock basis.
    """

    current = [
        row
        for row in admissions
        if int(row["material_batch_version"]) == batch_version and row["outcome"] == "admitted"
    ]
    bases = {(Decimal(row["delivered_quantity"]), str(row["delivered_unit"])) for row in current}
    result: dict[str, Any] = {
        "status": "no_delivery_basis",
        "delivered_quantity": None,
        "applied_quantity": None,
        "remaining_quantity": None,
        "unit_code": None,
        "admission_ids": [str(row["admission_id"]) for row in current],
        "application_ids": [str(row["material_application_id"]) for row in applications],
        "warning": "Учетная сверка не подтверждает физический остаток или приемку работы.",
    }
    if not bases:
        return result
    if len(bases) != 1:
        result["status"] = "conflicting_delivery_basis"
        return result
    delivered, unit = next(iter(bases))
    result["delivered_quantity"] = delivered
    result["unit_code"] = unit
    if version_count != 1 or any(
        int(row["material_batch_version"]) != batch_version for row in applications
    ):
        result["status"] = "revision_scope_unresolved"
        return result
    if any(str(row["unit_code"]) != unit for row in applications):
        result["status"] = "unit_scope_unresolved"
        return result
    applied = sum((Decimal(row["quantity"]) for row in applications), Decimal("0"))
    result["applied_quantity"] = applied
    result["remaining_quantity"] = delivered - applied
    result["status"] = "over_applied" if applied > delivered else "recorded_balance"
    return result
