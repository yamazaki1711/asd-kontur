"""Generic early Tender decision tests with changed, non-project values."""

# ruff: noqa: RUF001 -- Russian currency notation is intentional.

from __future__ import annotations

import pytest

from asd_kontur.tender.participation_decision import (
    TenderParticipationInputError,
    assess_tender_participation,
    project_price_ceiling,
)


def _ready_input() -> dict[str, object]:
    return {
        "company_scope_fit": "yes",
        "contract_acceptable": "yes",
        "conditions_feasible": "yes",
        "minimum_viable_price_rub": "800.00",
        "minimum_viable_price_reason": "Confirmed company estimate",
        "price_basis_confirmed": True,
    }


def _project_price(value: str = "1 000,00 руб.") -> list[dict[str, object]]:
    return [
        {
            "field": "nmck",
            "value": value,
            "source_locator_ids": ["locator-a"],
        }
    ]


@pytest.mark.parametrize(
    ("changed_field", "reason_field", "code"),
    [
        ("company_scope_fit", "company_scope_fit_reason", "PROFILE_MISMATCH"),
        ("contract_acceptable", "contract_acceptable_reason", "UNACCEPTABLE_CONTRACT"),
        ("conditions_feasible", "conditions_feasible_reason", "IMPOSSIBLE_TENDER_CONDITIONS"),
    ],
)
def test_human_declared_early_blocker_is_preserved(
    changed_field: str, reason_field: str, code: str
) -> None:
    values = _ready_input()
    values[changed_field] = "no"
    values[reason_field] = "Evidence-backed reviewer reason"
    result = assess_tender_participation(
        values,
        commercial_conditions=_project_price(),
        professional_issue_count=0,
        project_analysis_complete=True,
    )
    assert result["decision"] == "DO_NOT_PARTICIPATE"
    assert [item["code"] for item in result["blockers"]] == [code]


def test_project_ceiling_below_viable_cost_uses_decimal_and_common_basis() -> None:
    values = _ready_input()
    values["minimum_viable_price_rub"] = "1200.00"
    result = assess_tender_participation(
        values,
        commercial_conditions=_project_price(),
        professional_issue_count=0,
        project_analysis_complete=True,
    )
    assert result["decision"] == "DO_NOT_PARTICIPATE"
    assert result["blockers"][0]["code"] == "PRICE_BELOW_VIABLE_COST"
    assert result["project_price_ceiling"]["source_locator_ids"] == ["locator-a"]


def test_missing_company_or_cost_data_never_becomes_neutral_fit() -> None:
    result = assess_tender_participation(
        None,
        commercial_conditions=_project_price(),
        professional_issue_count=0,
        project_analysis_complete=True,
    )
    assert result["decision"] == "INSUFFICIENT_INPUT"
    assert result["blockers"] == []
    assert "company_scope_fit" in result["missing_inputs"]
    assert "minimum_viable_price_rub" in result["missing_inputs"]


def test_conflicting_project_prices_do_not_produce_arithmetic_decision() -> None:
    result = assess_tender_participation(
        _ready_input(),
        commercial_conditions=[*_project_price(), *_project_price("950,00 руб.")],
        professional_issue_count=0,
        project_analysis_complete=True,
    )
    assert result["decision"] == "INSUFFICIENT_INPUT"
    assert result["project_price_ceiling"]["state"] == "conflicting_values"
    assert "project_price_ceiling" in result["missing_inputs"]


def test_mismatched_price_basis_prevents_false_negative() -> None:
    values = _ready_input()
    values["minimum_viable_price_rub"] = "1200.00"
    values["price_basis_confirmed"] = False
    result = assess_tender_participation(
        values,
        commercial_conditions=_project_price(),
        professional_issue_count=0,
        project_analysis_complete=True,
    )
    assert result["decision"] == "INSUFFICIENT_INPUT"
    assert "price_basis_confirmation" in result["missing_inputs"]


def test_positive_decision_requires_completed_analysis_and_no_issues() -> None:
    conditional = assess_tender_participation(
        _ready_input(),
        commercial_conditions=_project_price(),
        professional_issue_count=2,
        project_analysis_complete=True,
    )
    complete = assess_tender_participation(
        _ready_input(),
        commercial_conditions=_project_price(),
        professional_issue_count=0,
        project_analysis_complete=True,
    )
    assert conditional["decision"] == "PARTICIPATE_SUBJECT_TO_CONDITIONS"
    assert complete["decision"] == "PARTICIPATE"


def test_price_parser_refuses_unscoped_or_non_ruble_values() -> None:
    assert project_price_ceiling([{"field": "vat", "value": "20%"}])["state"] == "not_established"
    assert (
        project_price_ceiling([{"field": "nmck", "value": "1000 USD"}])["state"]
        == "not_established"
    )


def test_negative_declaration_requires_a_reason() -> None:
    values = _ready_input()
    values["contract_acceptable"] = "no"
    with pytest.raises(TenderParticipationInputError, match="reason_required"):
        assess_tender_participation(
            values,
            commercial_conditions=_project_price(),
            professional_issue_count=0,
            project_analysis_complete=True,
        )


def test_contractor_cost_build_up_derives_viable_price_without_model_arithmetic() -> None:
    values = _ready_input()
    values["minimum_viable_price_rub"] = None
    values["minimum_viable_price_reason"] = ""
    values.update(
        {
            "cost_items": [
                {
                    "category": "materials",
                    "description": "Pipe procurement",
                    "quantity": "3.5",
                    "unit": "m",
                    "unit_rate_rub": "200.10",
                    "basis": "Signed supplier quotation",
                },
                {
                    "category": "logistics",
                    "description": "Site transport",
                    "quantity": "2",
                    "unit": "trip",
                    "unit_rate_rub": "150.00",
                    "basis": "Carrier quotation 2026",
                },
            ],
            "required_profit_rub": "50.00",
            "cost_scope_complete": True,
        }
    )
    result = assess_tender_participation(
        values,
        commercial_conditions=_project_price(),
        professional_issue_count=0,
        project_analysis_complete=True,
    )
    assert result["cost_build_up"]["cost_subtotal_rub"] == "1000.35"
    assert result["cost_build_up"]["derived_minimum_viable_price_rub"] == "1050.35"
    assert result["decision"] == "DO_NOT_PARTICIPATE"
    assert result["blockers"][0]["code"] == "PRICE_BELOW_VIABLE_COST"


def test_incomplete_cost_build_up_cannot_be_used_as_viability_gate() -> None:
    values = _ready_input()
    values["minimum_viable_price_rub"] = None
    values["minimum_viable_price_reason"] = ""
    values.update(
        {
            "cost_items": [
                {
                    "category": "materials",
                    "description": "Steel supply",
                    "quantity": "2",
                    "unit": "t",
                    "unit_rate_rub": "600.00",
                    "basis": "Supplier quotation",
                }
            ],
            "required_profit_rub": "100.00",
            "cost_scope_complete": False,
        }
    )
    result = assess_tender_participation(
        values,
        commercial_conditions=_project_price(),
        professional_issue_count=0,
        project_analysis_complete=True,
    )
    assert result["decision"] == "INSUFFICIENT_INPUT"
    assert result["cost_build_up"]["derived_minimum_viable_price_rub"] is None


def test_cost_build_up_rejects_unsupported_basis_and_conflicting_manual_total() -> None:
    values = _ready_input()
    values.update(
        {
            "cost_items": [
                {
                    "category": "labor",
                    "description": "Crew hours",
                    "quantity": "10",
                    "unit": "h",
                    "unit_rate_rub": "20.00",
                    "basis": "Company rate card",
                }
            ],
            "required_profit_rub": "10.00",
            "cost_scope_complete": True,
        }
    )
    with pytest.raises(TenderParticipationInputError, match="cost_build_up_conflict"):
        assess_tender_participation(
            values,
            commercial_conditions=_project_price(),
            professional_issue_count=0,
            project_analysis_complete=True,
        )
    values["minimum_viable_price_rub"] = None
    values["cost_items"][0]["basis"] = "unsure"  # type: ignore[index]
    with pytest.raises(TenderParticipationInputError, match="cost_item_basis_invalid"):
        assess_tender_participation(
            values,
            commercial_conditions=_project_price(),
            professional_issue_count=0,
            project_analysis_complete=True,
        )
