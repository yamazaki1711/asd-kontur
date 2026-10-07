"""A human revision decision is tied to exact Qwen text and its source."""

from __future__ import annotations

from uuid import uuid4

from asd_kontur.tender.contract_revision_review import (
    apply_revision_reviews,
    revision_review_candidates,
)


def _view() -> dict[str, object]:
    clause_id = str(uuid4())
    return {
        "clauses": [
            {
                "clause_id": clause_id,
                "clause_version": 1,
                "clause_key": "7.4",
                "source_version_id": str(uuid4()),
                "source_locator_id": str(uuid4()),
                "source_text": "The original condition applies.",
            }
        ],
        "revised_clauses": [
            {
                "revised_clause_id": str(uuid4()),
                "source_clause_id": clause_id,
                "source_clause_version": 1,
                "replacement_source_text": "The original condition applies.",
                "revised_text": "The changed condition applies.",
            }
        ],
    }


def test_review_is_source_bound_and_changes_become_stale() -> None:
    view = _view()
    candidate = revision_review_candidates(view)[0]
    decision = {
        "candidate_id": candidate["candidate_id"],
        "action": "confirmed",
        "original_value": {"candidate_digest": candidate["candidate_digest"]},
        "decided_at": "2026-10-07T00:00:00Z",
    }
    assert apply_revision_reviews([candidate], [decision])[0]["review_state"] == "confirmed"
    view["revised_clauses"][0]["revised_text"] = "A different proposed condition."
    changed = revision_review_candidates(view)[0]
    assert changed["candidate_digest"] != candidate["candidate_digest"]
    assert apply_revision_reviews([changed], [decision])[0]["review_state"] == "stale"
    view["clauses"][0]["source_text"] = "The source clause was revised."
    changed_again = revision_review_candidates(view)[0]
    assert changed_again["candidate_digest"] != changed["candidate_digest"]


def test_review_does_not_create_candidate_without_source_locator() -> None:
    view = _view()
    view["clauses"][0]["source_locator_id"] = None
    assert revision_review_candidates(view) == []
