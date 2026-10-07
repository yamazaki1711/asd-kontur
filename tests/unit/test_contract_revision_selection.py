"""A reviewer can select current proposals without editing model output."""

from uuid import uuid4

import pytest

from asd_kontur.tender.contract_revision_selection import (
    contract_revision_fingerprint,
    select_contract_revisions,
)
from asd_kontur.tender.revised_contract_candidate import RevisedContractCandidateError


def _view() -> dict[str, object]:
    first_id, second_id = str(uuid4()), str(uuid4())
    return {
        "clauses": [
            {
                "clause_id": "first",
                "clause_version": 1,
                "source_version_id": "changed-source-a",
                "source_text": "Original A",
            },
            {
                "clause_id": "second",
                "clause_version": 1,
                "source_version_id": "changed-source-b",
                "source_text": "Original B",
            },
        ],
        "revised_clauses": [
            {
                "revised_clause_id": first_id,
                "source_clause_id": "first",
                "source_clause_version": 1,
                "revised_text": "Proposed A",
            },
            {
                "revised_clause_id": second_id,
                "source_clause_id": "second",
                "source_clause_version": 1,
                "revised_text": "Proposed B",
            },
        ],
    }


def test_selection_keeps_only_chosen_current_proposal() -> None:
    view = _view()
    selected_id = view["revised_clauses"][1]["revised_clause_id"]
    selected = select_contract_revisions(
        view,
        revision_ids=[selected_id],
        fingerprint=contract_revision_fingerprint(view),
    )
    assert [item["revised_text"] for item in selected["revised_clauses"]] == ["Proposed B"]
    assert len(view["revised_clauses"]) == 2


def test_stale_and_unknown_selection_fail_closed() -> None:
    view = _view()
    identity = view["revised_clauses"][0]["revised_clause_id"]
    token = contract_revision_fingerprint(view)
    view["revised_clauses"][0]["revised_text"] = "New model wording"
    with pytest.raises(RevisedContractCandidateError, match="selection_stale"):
        select_contract_revisions(view, revision_ids=[identity], fingerprint=token)
    with pytest.raises(RevisedContractCandidateError, match="selection_stale"):
        select_contract_revisions(
            view,
            revision_ids=[str(uuid4())],
            fingerprint=contract_revision_fingerprint(view),
        )


@pytest.mark.parametrize("identities", [[], ["not-a-uuid"]])
def test_invalid_selection_fails_closed(identities: list[str]) -> None:
    view = _view()
    with pytest.raises(RevisedContractCandidateError, match="selection_invalid"):
        select_contract_revisions(
            view,
            revision_ids=identities,
            fingerprint=contract_revision_fingerprint(view),
        )
