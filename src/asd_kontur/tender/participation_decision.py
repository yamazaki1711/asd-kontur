"""Evidence-bounded Tender participation decision, without invented company data."""

# ruff: noqa: RUF001 -- Russian currency notation is intentional.

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from typing import Any

from asd_kontur.application_spine.models import semantic_digest

_PRICE_FIELDS = frozenset({"nmck", "initial_contract_price"})
_RUBLE_VALUE = re.compile(
    r"^\s*(?P<number>\d[\d\s\u00a0]*(?:[.,]\d{1,2})?)\s*(?:руб\.?|рубл\w*|₽|RUB)\s*$",
    re.IGNORECASE,
)
_DECISIONS = frozenset({"yes", "no", "unknown"})


class TenderParticipationInputError(ValueError):
    """The contractor assessment cannot be accepted as a scoped, explicit input."""


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
    cost = value.get("minimum_viable_price_rub")
    if cost in (None, ""):
        result["minimum_viable_price_rub"] = None
    else:
        try:
            amount = Decimal(str(cost))
        except (InvalidOperation, ValueError) as exc:
            raise TenderParticipationInputError("tender_participation_cost_invalid") from exc
        if not amount.is_finite() or amount <= 0 or amount.as_tuple().exponent < -2:
            raise TenderParticipationInputError("tender_participation_cost_invalid")
        result["minimum_viable_price_rub"] = format(amount, "f")
    result["price_basis_confirmed"] = value.get("price_basis_confirmed") is True
    cost_reason = " ".join(str(value.get("minimum_viable_price_reason") or "").split())
    if result["minimum_viable_price_rub"] is not None and len(cost_reason) < 8:
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
        "professional_issue_count": professional_issue_count,
        "project_analysis_complete": project_analysis_complete,
        "authority": "human_contractor_assessment_plus_source_derived_project_facts",
    }
    result["decision_digest"] = semantic_digest(result)
    return result
