"""Delivery is a batch basis, not an amount to add for each work."""

from decimal import Decimal

import pytest

from asd_kontur.support.material_balance import calculate_material_balance


def _admission(identity: str, quantity: str = "12.5", unit: str = "kg") -> dict[str, object]:
    return {
        "admission_id": identity,
        "material_batch_version": 1,
        "outcome": "admitted",
        "delivered_quantity": Decimal(quantity),
        "delivered_unit": unit,
    }


def _application(identity: str, quantity: str = "5.25", unit: str = "kg") -> dict[str, object]:
    return {
        "material_application_id": identity,
        "material_batch_version": 1,
        "quantity": Decimal(quantity),
        "unit_code": unit,
    }


def test_delivery_is_counted_once_for_multiple_works() -> None:
    result = calculate_material_balance(
        batch_version=1,
        version_count=1,
        admissions=[_admission("a"), _admission("b")],
        applications=[_application("x"), _application("y", "2.75")],
    )
    assert result["status"] == "recorded_balance"
    assert result["delivered_quantity"] == Decimal("12.5")
    assert result["applied_quantity"] == Decimal("8.00")
    assert result["remaining_quantity"] == Decimal("4.50")
    assert result["admission_ids"] == ["a", "b"]


@pytest.mark.parametrize(
    ("admissions", "applications", "version_count", "status"),
    [
        ([], [], 1, "no_delivery_basis"),
        ([_admission("a"), _admission("b", "14")], [], 1, "conflicting_delivery_basis"),
        ([_admission("a")], [_application("x", unit="t")], 1, "unit_scope_unresolved"),
        ([_admission("a")], [_application("x")], 2, "revision_scope_unresolved"),
        ([_admission("a")], [_application("x", "13")], 1, "over_applied"),
    ],
)
def test_balance_refuses_unsupported_remaining_quantity(
    admissions: list[dict[str, object]],
    applications: list[dict[str, object]],
    version_count: int,
    status: str,
) -> None:
    result = calculate_material_balance(
        batch_version=1,
        version_count=version_count,
        admissions=admissions,
        applications=applications,
    )
    assert result["status"] == status
    if status in {
        "no_delivery_basis",
        "conflicting_delivery_basis",
        "unit_scope_unresolved",
        "revision_scope_unresolved",
    }:
        assert result["remaining_quantity"] is None
