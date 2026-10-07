"""Evidence-bounded Tender participation decision, without invented company data."""

# ruff: noqa: RUF001 -- Russian currency notation is intentional.

from __future__ import annotations

import re
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any

from asd_kontur.application_spine.models import semantic_digest

_PRICE_FIELDS = frozenset({"nmck", "initial_contract_price"})
_RUBLE_VALUE = re.compile(
    r"^\s*(?P<number>\d[\d\s\u00a0]*(?:[.,]\d{1,2})?)\s*(?:руб\.?|рубл\w*|₽|RUB)\s*$",
    re.IGNORECASE,
)
_DECISIONS = frozenset({"yes", "no", "unknown"})
_COST_CATEGORIES = frozenset(
    {"labor", "materials", "equipment", "subcontract", "logistics", "site", "other"}
)
_RUBLE_CENT = Decimal("0.01")


class TenderParticipationInputError(ValueError):
    """The contractor assessment cannot be accepted as a scoped, explicit input."""


def _decimal_input(value: object, *, field: str, scale: int, positive: bool) -> Decimal:
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise TenderParticipationInputError(f"tender_participation_{field}_invalid") from exc
    exponent = amount.as_tuple().exponent
    if (
        not amount.is_finite()
        or (amount <= 0 if positive else amount < 0)
        or not isinstance(exponent, int)
        or exponent < -scale
        or amount > Decimal("1000000000000000")
    ):
        raise TenderParticipationInputError(f"tender_participation_{field}_invalid")
    return amount


def _cost_build_up(value: dict[str, Any]) -> dict[str, Any]:
    raw_items = value.get("cost_items") or []
    if not isinstance(raw_items, list) or len(raw_items) > 50:
        raise TenderParticipationInputError("tender_participation_cost_items_invalid")
    items: list[dict[str, str]] = []
    total = Decimal("0")
    for raw in raw_items:
        if not isinstance(raw, dict) or raw.get("category") not in _COST_CATEGORIES:
            raise TenderParticipationInputError("tender_participation_cost_item_invalid")
        description = " ".join(str(raw.get("description") or "").split())
        unit = " ".join(str(raw.get("unit") or "").split())
        basis = " ".join(str(raw.get("basis") or "").split())
        if not (3 <= len(description) <= 200 and 1 <= len(unit) <= 30 and 8 <= len(basis) <= 1000):
            raise TenderParticipationInputError("tender_participation_cost_item_basis_invalid")
        quantity = _decimal_input(raw.get("quantity"), field="quantity", scale=6, positive=True)
        rate = _decimal_input(raw.get("unit_rate_rub"), field="unit_rate", scale=2, positive=False)
        amount = (quantity * rate).quantize(_RUBLE_CENT, rounding=ROUND_HALF_UP)
        total += amount
        items.append(
            {
                "category": str(raw["category"]),
                "description": description,
                "quantity": format(quantity, "f"),
                "unit": unit,
                "unit_rate_rub": format(rate, "f"),
                "amount_rub": format(amount, ".2f"),
                "basis": basis,
            }
        )
    complete = value.get("cost_scope_complete") is True
    profit_raw = value.get("required_profit_rub")
    profit = (
        None
        if profit_raw in (None, "")
        else _decimal_input(profit_raw, field="required_profit", scale=2, positive=False)
    )
    if complete and (not items or profit is None):
        raise TenderParticipationInputError("tender_participation_complete_cost_basis_missing")
    if complete and profit is not None and total + profit <= 0:
        raise TenderParticipationInputError("tender_participation_complete_cost_zero")
    return {
        "items": items,
        "scope_complete": complete,
        "cost_subtotal_rub": format(total, ".2f"),
        "required_profit_rub": format(profit, ".2f") if profit is not None else None,
        "derived_minimum_viable_price_rub": (
            format(total + profit, ".2f") if complete and profit is not None else None
        ),
        "authority": "contractor_supplied_quantities_rates_and_scope_confirmation",
    }


def validate_contractor_assessment(value: dict[str, Any]) -> dict[str, Any]:
    """Validate human declarations without treating them as document-derived facts."""

    result: dict[str, Any] = {}
    for field in ("company_scope_fit", "contract_acceptable", "conditions_feasible"):
        decision = str(value.get(field) or "unknown")
        if decision not in _DECISIONS:
            raise TenderParticipationInputError(f"tender_participation_{field}_invalid")
        result[field] = decision
        reason = " ".join(str(value.get(f"{field}_reason") or "").split())
        if decision == "no" and len(reason) < 8:
            raise TenderParticipationInputError(f"tender_participation_{field}_reason_required")
        if len(reason) > 1000:
            raise TenderParticipationInputError(f"tender_participation_{field}_reason_too_long")
        result[f"{field}_reason"] = reason
    build_up = _cost_build_up(value)
    result["cost_items"] = build_up["items"]
    result["cost_scope_complete"] = build_up["scope_complete"]
    result["required_profit_rub"] = build_up["required_profit_rub"]
    cost = value.get("minimum_viable_price_rub")
    if cost in (None, ""):
        result["minimum_viable_price_rub"] = None
    else:
        amount = _decimal_input(cost, field="cost", scale=2, positive=True)
        result["minimum_viable_price_rub"] = format(amount, "f")
    derived = build_up["derived_minimum_viable_price_rub"]
    if derived is not None:
        if cost not in (None, "") and Decimal(result["minimum_viable_price_rub"]) != Decimal(
            derived
        ):
            raise TenderParticipationInputError("tender_participation_cost_build_up_conflict")
        result["minimum_viable_price_rub"] = derived
    result["price_basis_confirmed"] = value.get("price_basis_confirmed") is True
    cost_reason = " ".join(str(value.get("minimum_viable_price_reason") or "").split())
    if result["minimum_viable_price_rub"] is not None and derived is None and len(cost_reason) < 8:
        raise TenderParticipationInputError("tender_participation_cost_reason_required")
    if len(cost_reason) > 1000:
        raise TenderParticipationInputError("tender_participation_cost_reason_too_long")
    result["minimum_viable_price_reason"] = cost_reason
    return result


def project_price_ceiling(commercial_conditions: object) -> dict[str, Any]:
    """Parse only Qwen-classified price-ceiling facts with an exact RUB amount."""

    candidates: list[tuple[Decimal, dict[str, Any]]] = []
    for raw in commercial_conditions if isinstance(commercial_conditions, (list, tuple)) else ():
        if not isinstance(raw, dict) or raw.get("field") not in _PRICE_FIELDS:
            continue
        match = _RUBLE_VALUE.fullmatch(str(raw.get("value") or ""))
        if match is None:
            continue
        number = match.group("number").replace(" ", "").replace("\u00a0", "").replace(",", ".")
        try:
            amount = Decimal(number)
        except InvalidOperation:
            continue
        if amount <= 0:
            continue
        candidates.append((amount, raw))
    distinct = {amount for amount, _ in candidates}
    if not distinct:
        return {"state": "not_established", "value_rub": None, "source_locator_ids": []}
    if len(distinct) != 1:
        return {
            "state": "conflicting_values",
            "value_rub": None,
            "source_locator_ids": sorted(
                {
                    str(locator)
                    for _, row in candidates
                    for locator in row.get("source_locator_ids") or ()
                }
            ),
        }
    amount = next(iter(distinct))
    return {
        "state": "established",
        "value_rub": format(amount, "f"),
        "source_locator_ids": sorted(
            {
                str(locator)
                for _, row in candidates
                for locator in row.get("source_locator_ids") or ()
            }
        ),
    }


def assess_tender_participation(
    contractor_assessment: dict[str, Any] | None,
    *,
    commercial_conditions: object,
    professional_issue_count: int,
    project_analysis_complete: bool,
) -> dict[str, Any]:
    """Apply four early gates; never turn missing inputs into positive or negative evidence."""

    assessment = validate_contractor_assessment(contractor_assessment or {})
    cost_build_up = _cost_build_up(assessment)
    ceiling = project_price_ceiling(commercial_conditions)
    blockers: list[dict[str, str]] = []
    missing: list[str] = []
    for field, code in (
        ("company_scope_fit", "PROFILE_MISMATCH"),
        ("contract_acceptable", "UNACCEPTABLE_CONTRACT"),
        ("conditions_feasible", "IMPOSSIBLE_TENDER_CONDITIONS"),
    ):
        decision = assessment[field]
        if decision == "no":
            blockers.append({"code": code, "reason": assessment[f"{field}_reason"]})
        elif decision == "unknown":
            missing.append(field)
    cost = assessment["minimum_viable_price_rub"]
    if cost is None:
        missing.append("minimum_viable_price_rub")
    if ceiling["state"] != "established":
        missing.append("project_price_ceiling")
    if not assessment["price_basis_confirmed"]:
        missing.append("price_basis_confirmation")
    if (
        cost is not None
        and ceiling["value_rub"] is not None
        and assessment["price_basis_confirmed"]
    ):
        if Decimal(ceiling["value_rub"]) < Decimal(cost):
            blockers.append(
                {
                    "code": "PRICE_BELOW_VIABLE_COST",
                    "reason": (
                        f"Documented ceiling {ceiling['value_rub']} RUB is below the "
                        f"contractor-declared minimum viable price {cost} RUB "
                        "on a confirmed common basis."
                    ),
                }
            )
    if blockers:
        decision = "DO_NOT_PARTICIPATE"
    elif missing:
        decision = "INSUFFICIENT_INPUT"
    elif professional_issue_count or not project_analysis_complete:
        decision = "PARTICIPATE_SUBJECT_TO_CONDITIONS"
    else:
        decision = "PARTICIPATE"
    result = {
        "decision": decision,
        "blockers": blockers,
        "missing_inputs": sorted(set(missing)),
        "project_price_ceiling": ceiling,
        "contractor_assessment": assessment,
        "cost_build_up": cost_build_up,
        "professional_issue_count": professional_issue_count,
        "project_analysis_complete": project_analysis_complete,
        "authority": "human_contractor_assessment_plus_source_derived_project_facts",
    }
    result["decision_digest"] = semantic_digest(result)
    return result
