"""Contract duties reach Support without being promoted to accepted facts."""

from types import SimpleNamespace
from uuid import uuid4

from asd_kontur.application_spine.services import ProductSpineService
from asd_kontur.support.contract_handover import contract_obligation_handover


def test_contract_obligations_keep_party_condition_and_source() -> None:
    rows = contract_obligation_handover(
        {
            "clauses": [
                {
                    "clause_id": "payment-4",
                    "clause_key": "4.2",
                    "source_version_id": "source-a",
                    "source_locator_id": "locator-a",
                    "source_name": "contract.docx",
                    "source_page": 3,
                    "customer_obligation": "Pay accepted work.",
                    "contractor_obligation": "Submit acceptance records.",
                    "condition": "After acceptance.",
                },
                {
                    "clause_id": "definition-1",
                    "source_version_id": "source-a",
                    "source_locator_id": "locator-b",
                    "customer_obligation": None,
                },
                {
                    "clause_id": "unsupported",
                    "customer_obligation": "Do something without source.",
                },
            ]
        }
    )
    assert len(rows) == 2
    assert {row["party"] for row in rows} == {"customer", "contractor"}
    assert all(row["source_locator_id"] == "locator-a" for row in rows)
    assert all(row["condition"] == "After acceptance." for row in rows)
    assert all(
        row["authority"] == "qwen_extracted_candidate_requires_contract_review" for row in rows
    )


def test_duplicate_extracted_clause_does_not_duplicate_handover() -> None:
    clause = {
        "clause_id": "warranty-2",
        "source_version_id": "source-b",
        "source_locator_id": "locator-c",
        "contractor_obligation": "Repair defects in the stated warranty period.",
    }
    assert len(contract_obligation_handover({"clauses": [clause, clause]})) == 1


def test_support_view_reads_contract_only_with_same_workspace_scope() -> None:
    workspace_id = uuid4()
    calls: list[tuple[str, str, object]] = []

    def support_view(**kwargs: object) -> dict[str, object]:
        calls.append(("support", str(kwargs["owner_identity_id"]), kwargs["workspace_id"]))
        return {"requirements": [], "matrix": None, "package": None}

    def contract_view(**kwargs: object) -> dict[str, object]:
        calls.append(("contract", str(kwargs["owner_identity_id"]), kwargs["workspace_id"]))
        return {"clauses": []}

    service = object.__new__(ProductSpineService)
    service._support_production = SimpleNamespace(view=support_view)
    service._tender_contract_analysis = SimpleNamespace(latest=contract_view)
    result = service.support_production_view(owner_identity_id="owner-a", workspace_id=workspace_id)
    assert calls == [
        ("support", "owner-a", workspace_id),
        ("contract", "owner-a", workspace_id),
    ]
    assert result["contract_obligation_candidates"] == []
