"""A human revision decision is tied to exact Qwen text and its source."""

from __future__ import annotations

import io
import zipfile
from copy import deepcopy
from types import SimpleNamespace
from uuid import uuid4

import pytest

from asd_kontur.application_spine.services import ProductSpineService
from asd_kontur.tender.contract_revision_review import (
    apply_revision_reviews,
    revision_review_candidates,
)
from asd_kontur.tender.revised_contract_candidate import RevisedContractCandidateError


def _view() -> dict[str, object]:
    clause_id = str(uuid4())
    item_id = str(uuid4())
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
                "disagreement_item_id": item_id,
                "source_clause_id": clause_id,
                "source_clause_version": 1,
                "replacement_source_text": "The original condition applies.",
                "revised_text": "The changed condition applies.",
            }
        ],
        "disagreement_items": [
            {
                "item_id": item_id,
                "clause_id": clause_id,
                "clause_version": 1,
                "proposed_clause_text": "The changed condition applies.",
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


def test_reviewed_package_uses_server_decisions_not_client_ids() -> None:
    view = _view()
    second = deepcopy(view["revised_clauses"][0])
    second["revised_clause_id"] = str(uuid4())
    second["revised_text"] = "A second changed condition."
    second["disagreement_item_id"] = str(uuid4())
    view["revised_clauses"].append(second)
    view["disagreement_items"].append(
        {
            "item_id": second["disagreement_item_id"],
            "clause_id": second["source_clause_id"],
            "clause_version": 1,
            "proposed_clause_text": second["revised_text"],
        }
    )
    candidates = revision_review_candidates(view)
    decision = {
        "candidate_id": candidates[1]["candidate_id"],
        "action": "confirmed",
        "original_value": {"candidate_digest": candidates[1]["candidate_digest"]},
    }
    service = ProductSpineService.__new__(ProductSpineService)
    service._tender_contract_analysis = SimpleNamespace(latest=lambda **kwargs: view)
    service._contract_revision_reviews = SimpleNamespace(
        latest_decisions=lambda **kwargs: [decision]
    )
    selected_views: list[dict[str, object]] = []
    protocols: list[bytes] = []

    def render(**kwargs: object) -> tuple[bytes, int]:
        selected_views.append(kwargs["view"])
        protocols.append(kwargs["protocol_docx"])
        return b"synthetic-reviewed-package", 1

    service._render_revised_contract_source_package = render
    output = service.tender_reviewed_contract_package(
        owner_identity_id="owner:synthetic", workspace_id=uuid4()
    )
    assert b"".join(output.chunks) == b"synthetic-reviewed-package"
    assert [
        item["revised_clause_id"] for item in selected_views[0]["revised_clauses"]
    ] == [candidates[1]["candidate_id"]]
    assert [item["item_id"] for item in selected_views[0]["disagreement_items"]] == [
        second["disagreement_item_id"]
    ]
    with zipfile.ZipFile(io.BytesIO(protocols[0])) as package:
        xml = package.read("word/document.xml").decode()
    assert "A second changed condition." in xml
    assert "The changed condition applies." not in xml

    service._contract_revision_reviews = SimpleNamespace(latest_decisions=lambda **kwargs: [])
    with pytest.raises(
        RevisedContractCandidateError, match="reviewed_contract_revisions_unavailable"
    ):
        service.tender_reviewed_contract_package(
            owner_identity_id="owner:synthetic", workspace_id=uuid4()
        )
