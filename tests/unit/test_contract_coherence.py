"""Changed-corpus qualification of bounded contract-revision coherence inputs."""

# ruff: noqa: RUF001 -- Russian contract examples are intentional.

from __future__ import annotations

import io
import json
import zipfile

import pytest

from asd_kontur.document_understanding.qwen_semantic import QwenSemanticFailure
from asd_kontur.tender.contract_analysis_report import render_tender_contract_analysis_docx
from asd_kontur.tender.contract_coherence import (
    contract_coherence_job_key,
    contract_coherence_tasks,
    unreviewed_explicit_reference_count,
)
from asd_kontur.tender.qwen_contract_coherence import (
    QwenContractCoherenceReviewer,
    parse_contract_coherence,
)


def _view(*, conflicting: bool) -> dict[str, object]:
    return {
        "clauses": [
            {
                "clause_id": "payment-a",
                "clause_version": 1,
                "source_version_id": "source-a",
                "source_locator_id": "locator-a",
                "source_page": 3,
                "display_clause_ref": "4.1",
                "category": "payment",
                "source_text": "4.1. Customer pays within ten days of acceptance.",
            },
            {
                "clause_id": "payment-b",
                "clause_version": 1,
                "source_version_id": "source-b",
                "source_locator_id": "locator-b",
                "source_page": 9,
                "display_clause_ref": "7.3",
                "category": "payment",
                "source_text": (
                    "7.3. Payment is due only after investor funding."
                    if conflicting
                    else "7.3. Customer may pay early."
                ),
            },
            {
                "clause_id": "warranty-c",
                "clause_version": 1,
                "source_version_id": "source-c",
                "source_locator_id": "locator-c",
                "source_page": 5,
                "display_clause_ref": "9.2",
                "category": "warranty",
                "source_text": "9.2. Contractor repairs its own defects for two years.",
            },
        ],
        "revised_clauses": [
            {
                "revised_clause_id": "revision-a",
                "source_clause_id": "payment-a",
                "source_clause_version": 1,
                "revised_text": "4.1. Customer pays within ten days of acceptance.",
            }
        ],
    }


def test_coherence_key_uses_result_schema_generation() -> None:
    assert contract_coherence_job_key("sha256:input") == (
        "contract-coherence:qwen-contract-coherence-v2:schema-0134:sha256:input"
    )


def test_changed_contract_routes_related_clause_without_claiming_full_coverage() -> None:
    tasks = contract_coherence_tasks(_view(conflicting=True))
    assert len(tasks) == 1
    task = tasks[0]
    assert [item["clause_id"] for item in task["related_clauses"]] == ["payment-b"]
    assert task["coverage"] == {
        "total_other_clauses": 2,
        "selected_other_clauses": 1,
        "omitted_other_clauses": 1,
        "reverse_reference_clauses": 0,
        "selected_reverse_reference_clauses": 0,
        "total_revisions": 1,
        "scheduled_revision_limit": 16,
    }
    assert contract_coherence_tasks(_view(conflicting=True)) == tasks
    changed = _view(conflicting=True)
    changed["clauses"][1]["source_text"] = "7.3. Customer pays after signed acceptance."
    assert contract_coherence_tasks(changed)[0]["context_digest"] != task["context_digest"]


def test_distant_clause_explicitly_referring_to_revised_clause_enters_review() -> None:
    view = _view(conflicting=False)
    view["clauses"] = [
        view["clauses"][0],
        {
            "clause_id": "termination-far",
            "clause_version": 1,
            "source_version_id": "other-source",
            "source_locator_id": "locator-far",
            "source_page": 80,
            "display_clause_ref": "11.7",
            "category": "termination",
            "source_text": (
                "11.7. В случае, указанном в п. 4.1 настоящего договора, "
                "Заказчик вправе приостановить оплату."
            ),
        },
    ]
    tasks = contract_coherence_tasks(view)
    assert len(tasks) == 1
    assert [item["clause_id"] for item in tasks[0]["related_clauses"]] == ["termination-far"]
    assert tasks[0]["coverage"]["reverse_reference_clauses"] == 1
    assert tasks[0]["coverage"]["selected_reverse_reference_clauses"] == 1


def test_explicit_cross_references_overflow_into_separate_bounded_review() -> None:
    view = _view(conflicting=False)
    view["clauses"] = [view["clauses"][0]] + [
        {
            "clause_id": f"related-{index:02d}",
            "clause_version": 1,
            "source_version_id": "source-a",
            "source_locator_id": f"locator-{index:02d}",
            "source_page": index + 20,
            "display_clause_ref": f"8.{index}",
            "category": "scope",
            "source_text": f"8.{index}. Условия п. 4.1 применяются к этапу {index}.",
        }
        for index in range(1, 15)
    ]
    tasks = contract_coherence_tasks(view)
    assert len(tasks) == 2
    assert len(tasks[0]["related_clauses"]) == 12
    assert len(tasks[1]["related_clauses"]) == 2
    ids = [clause["clause_id"] for task in tasks for clause in task["related_clauses"]]
    assert len(ids) == len(set(ids)) == 14
    assert tasks[1]["coverage"]["review_segment"] == "explicit_reference_overflow"
    assert tasks[1]["coverage"]["total_explicit_reference_overflow"] == 2
    assert tasks[0]["context_digest"] != tasks[1]["context_digest"]
    assert contract_coherence_tasks(view) == tasks
    assert unreviewed_explicit_reference_count(view, tasks) == 0
    overflow_result = parse_contract_coherence(
        json.dumps(
            {
                "conflicts": [
                    {
                        "other_clause_id": "related-13",
                        "proposal_quote": "within ten days of acceptance",
                        "other_quote": "Условия п. 4.1 применяются к этапу 13",
                        "conflict": "The payment and stage conditions require reconciliation.",
                        "contractor_consequence": "The payment trigger may be disputed.",
                        "recommended_action": "Agree the controlling clause wording.",
                        "confidence": 0.8,
                        "uncertainty": None,
                    }
                ]
            }
        ),
        context=tasks[1],
    )
    assert overflow_result[0]["other_clause_id"] == "related-13"


def test_unroutable_explicit_reference_remains_visible_as_coverage_gap() -> None:
    view = _view(conflicting=False)
    view["clauses"] = [
        view["clauses"][0],
        {
            "clause_id": "long-cross-reference",
            "clause_version": 1,
            "source_version_id": "source-a",
            "source_locator_id": "locator-long",
            "source_page": 90,
            "display_clause_ref": "12.4",
            "category": "scope",
            "source_text": "12.4. Согласно п. 4.1 " + "условия  " * 300,
        },
    ]
    tasks = contract_coherence_tasks(view)
    assert tasks == ()
    assert unreviewed_explicit_reference_count(view, tasks) == 1


def test_review_uses_effective_wording_when_related_clause_is_also_revised() -> None:
    view = _view(conflicting=True)
    view["revised_clauses"].append(
        {
            "revised_clause_id": "revision-b",
            "source_clause_id": "payment-b",
            "source_clause_version": 1,
            "revised_text": "7.3. Payment is due after design approval.",
        }
    )
    task = next(
        item for item in contract_coherence_tasks(view) if item["revision_id"] == "revision-a"
    )
    related = task["related_clauses"][0]
    assert related["source_text"] == "7.3. Payment is due only after investor funding."
    assert related["proposed_candidate_text"] == "7.3. Payment is due after design approval."
    response = {
        "conflicts": [
            {
                "other_clause_id": "payment-b",
                "proposal_quote": "within ten days of acceptance",
                "other_quote": "after design approval",
                "conflict": "The triggers differ.",
                "contractor_consequence": "Payment may be delayed.",
                "recommended_action": "Align the two proposed clauses.",
                "confidence": 0.8,
                "uncertainty": None,
            }
        ]
    }
    accepted = parse_contract_coherence(json.dumps(response), context=task)
    assert accepted[0]["other_revision_id"] == "revision-b"
    assert accepted[0]["other_text_kind"] == "proposed_revision"
    view["coherence_review"] = {"conflicts": [{"revision_id": "revision-a", **accepted[0]}]}
    rendered = render_tender_contract_analysis_docx(view)
    with zipfile.ZipFile(io.BytesIO(rendered)) as package:
        body = package.read("word/document.xml").decode("utf-8")
    assert "Предлагаемая редакция:" in body
    assert "after design approval" in body
    response["conflicts"][0]["other_quote"] = "only after investor funding"
    with pytest.raises(QwenSemanticFailure, match="qwen_contract_coherence_source_invalid"):
        parse_contract_coherence(json.dumps(response), context=task)


def test_removed_cross_reference_is_not_a_false_coverage_gap() -> None:
    view = _view(conflicting=False)
    view["clauses"] = [
        view["clauses"][0],
        {
            "clause_id": "scope-b",
            "clause_version": 1,
            "source_version_id": "source-b",
            "source_locator_id": "locator-b",
            "source_page": 88,
            "display_clause_ref": "12.8",
            "category": "scope",
            "source_text": "12.8. Исполнение производится согласно п. 4.1.",
        },
    ]
    view["revised_clauses"].append(
        {
            "revised_clause_id": "revision-b",
            "source_clause_id": "scope-b",
            "source_clause_version": 1,
            "revised_text": "12.8. Исполнение производится после приёмки результата.",
        }
    )
    tasks = contract_coherence_tasks(view)
    assert not any(task["revision_id"] == "revision-a" for task in tasks)
    assert unreviewed_explicit_reference_count(view, tasks) == 0


def test_same_number_as_measurement_does_not_create_contract_reference() -> None:
    view = _view(conflicting=False)
    view["clauses"] = [
        view["clauses"][0],
        {
            "clause_id": "quantity-far",
            "clause_version": 1,
            "source_version_id": "other-source",
            "source_locator_id": "locator-far",
            "source_page": 80,
            "display_clause_ref": "11.7",
            "category": "scope",
            "source_text": "11.7. Объём работ составляет 4.1 м³ по ведомости.",
        },
    ]
    assert contract_coherence_tasks(view) == ()


def test_proposal_requires_explicit_clause_reference_not_numeric_similarity() -> None:
    view = _view(conflicting=False)
    view["clauses"] = [
        view["clauses"][0],
        {
            "clause_id": "liability-far",
            "clause_version": 1,
            "source_version_id": "other-source",
            "source_locator_id": "locator-far",
            "source_page": 80,
            "display_clause_ref": "11.7",
            "category": "liability",
            "source_text": "11.7. Liability is limited to direct loss.",
        },
    ]
    view["revised_clauses"][0]["revised_text"] = "4.1. The material mass is 11.7 tonnes."
    assert contract_coherence_tasks(view) == ()
    view["revised_clauses"][0]["revised_text"] = (
        "4.1. Payment remains subject to clause 11.7 of this agreement."
    )
    tasks = contract_coherence_tasks(view)
    assert len(tasks) == 1
    assert [item["clause_id"] for item in tasks[0]["related_clauses"]] == ["liability-far"]


def test_exact_two_sided_quotes_required_for_candidate_conflict() -> None:
    task = contract_coherence_tasks(_view(conflicting=True))[0]
    valid = {
        "conflicts": [
            {
                "other_clause_id": "payment-b",
                "proposal_quote": "within ten days of acceptance",
                "other_quote": "only after investor funding",
                "conflict": "The payment triggers differ.",
                "contractor_consequence": "The payment date is uncertain.",
                "recommended_action": "Agree one trigger and amend both clauses.",
                "confidence": 0.9,
                "uncertainty": None,
            }
        ]
    }
    parsed = parse_contract_coherence(json.dumps(valid), context=task)
    assert len(parsed) == 1
    assert parsed[0]["other_source_locator_id"] == "locator-b"
    assert parsed[0]["other_source_version_id"] == "source-b"
    invalid = json.loads(json.dumps(valid))
    invalid["conflicts"][0]["other_quote"] = "a date invented by the model"
    with pytest.raises(QwenSemanticFailure, match="qwen_contract_coherence_source_invalid"):
        parse_contract_coherence(json.dumps(invalid), context=task)
    invalid["conflicts"][0]["other_quote"] = "only after investor funding"
    invalid["conflicts"][0]["other_clause_id"] = "unseen clause"
    with pytest.raises(QwenSemanticFailure, match="qwen_contract_coherence_source_invalid"):
        parse_contract_coherence(json.dumps(invalid), context=task)


def test_benign_clause_can_return_no_conflict_without_whole_contract_approval() -> None:
    task = contract_coherence_tasks(_view(conflicting=False))[0]
    assert parse_contract_coherence('{"conflicts":[]}', context=task) == []
    assert task["coverage"]["omitted_other_clauses"] == 1


def test_qwen_reviewer_records_exact_context_and_bounded_scope(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    task = contract_coherence_tasks(_view(conflicting=False))[0]
    monkeypatch.setattr(
        "asd_kontur.tender.qwen_contract_coherence._complete",
        lambda *_args, **_kwargs: '{"conflicts":[]}',
    )
    result = QwenContractCoherenceReviewer("http://127.0.0.1:8790/generate").review(task)
    assert result["context_digest"] == task["context_digest"]
    assert result["review_scope"] == "selected_related_clauses_only"
    assert result["conflicts"] == []


def test_editable_contract_report_shows_bounded_conflict_and_source_passages() -> None:
    view = _view(conflicting=True)
    view["coherence_review"] = {
        "accepted_contexts": 1,
        "scheduled_contexts": 1,
        "conflicts": [
            {
                "revision_id": "revision-a",
                "other_clause_id": "payment-b",
                "proposal_quote": "within ten days of acceptance",
                "other_quote": "only after investor funding",
                "conflict": "The payment triggers differ.",
                "contractor_consequence": "The payment date is uncertain.",
                "recommended_action": "Agree one trigger and amend both clauses.",
            }
        ],
    }
    rendered = render_tender_contract_analysis_docx(view)
    with zipfile.ZipFile(io.BytesIO(rendered)) as package:
        body = package.read("word/document.xml").decode("utf-8")
    assert "Возможные противоречия предлагаемых редакций" in body
    assert "within ten days of acceptance" in body
    assert "only after investor funding" in body
    assert "согласованность всего договора" in body
