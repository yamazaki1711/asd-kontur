"""Disposable PostgreSQL acceptance for source-bound contract revision review."""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest
import sqlalchemy as sa

from asd_kontur.application_spine.auth import OwnerAuthService
from asd_kontur.application_spine.config import SessionProfile, SpineSettings
from asd_kontur.tender.contract_revision_review import (
    ContractRevisionReviewError,
    ContractRevisionReviewRepository,
    apply_revision_reviews,
    revision_review_candidates,
)

from .conftest import PostgreSQLEnvironment
from .test_ai_vlm_harness import _seed_source
from .test_workspace_lifecycle import create_tenant

pytestmark = pytest.mark.postgres


def test_revision_decision_is_scoped_idempotent_and_invalidated(
    postgres_environment: PostgreSQLEnvironment, tmp_path: Path
) -> None:
    tenant = create_tenant(postgres_environment)
    unrelated = create_tenant(postgres_environment)
    source_id, locator_id = _seed_source(postgres_environment, tenant)
    store = tmp_path / "objects"
    archive = tmp_path / "archives"
    store.mkdir()
    archive.mkdir()
    settings = SpineSettings(
        database_url=postgres_environment.application_engine.url.render_as_string(
            hide_password=False
        ),
        lifecycle_database_url=postgres_environment.lifecycle_engine.url.render_as_string(
            hide_password=False
        ),
        worker_database_url=postgres_environment.document_worker_engine.url.render_as_string(
            hide_password=False
        ),
        destruction_database_url=postgres_environment.destruction_engine.url.render_as_string(
            hide_password=False
        ),
        object_store_root=store,
        archive_store_root=archive,
        session_profile=SessionProfile.DEVELOPMENT_LOOPBACK,
        audit_pepper="synthetic-revision-review-pepper",
    )
    owner = OwnerAuthService(postgres_environment.application_engine, settings).bootstrap_owner(
        username="changed-revision-review-owner",
        password="Changed-Revision-Review-Password-42!",
        display_name="Changed revision review owner",
    )
    read_only = OwnerAuthService(postgres_environment.application_engine, settings).bootstrap_owner(
        username="changed-revision-read-only",
        password="Changed-Revision-Read-Only-Password-42!",
        display_name="Changed revision read only owner",
    )
    with postgres_environment.owner_engine.begin() as connection:
        connection.execute(
            sa.text(
                "INSERT INTO application.owner_organization_grants VALUES "
                "(:owner,:organization,ARRAY['workspace.read','tender.review'],1,CURRENT_TIMESTAMP)"
            ),
            {"owner": owner, "organization": tenant.organization_id},
        )
        connection.execute(
            sa.text(
                "INSERT INTO application.owner_organization_grants VALUES "
                "(:owner,:organization,ARRAY['workspace.read'],1,CURRENT_TIMESTAMP)"
            ),
            {"owner": read_only, "organization": tenant.organization_id},
        )
    clause_id = str(uuid4())
    view = {
        "clauses": [
            {
                "clause_id": clause_id,
                "clause_version": 1,
                "clause_key": "8.2",
                "source_version_id": str(source_id),
                "source_locator_id": str(locator_id),
                "source_text": "Customer approves payment at its discretion.",
            }
        ],
        "revised_clauses": [
            {
                "revised_clause_id": str(uuid4()),
                "source_clause_id": clause_id,
                "source_clause_version": 1,
                "revised_text": "Payment follows documented acceptance.",
            }
        ],
    }
    candidate = revision_review_candidates(view)[0]
    repository = ContractRevisionReviewRepository(postgres_environment.application_engine)
    command = {
        "owner_identity_id": owner,
        "workspace_id": tenant.workspace_id,
        "candidate": candidate,
        "expected_digest": candidate["candidate_digest"],
        "action": "confirmed",
        "reason": "Checked exact clause and proposed wording.",
        "idempotency_key": "changed-revision-review-001",
    }
    assert repository.record(**command)["idempotent_replay"] is False
    assert repository.record(**command)["idempotent_replay"] is True
    decisions = repository.latest_decisions(
        owner_identity_id=owner, workspace_id=tenant.workspace_id
    )
    assert len(decisions) == 1
    assert apply_revision_reviews([candidate], decisions)[0]["review_state"] == "confirmed"
    view["revised_clauses"][0]["revised_text"] = "Changed wording after review."
    changed = revision_review_candidates(view)[0]
    assert apply_revision_reviews([changed], decisions)[0]["review_state"] == "stale"
    with pytest.raises(ContractRevisionReviewError, match="idempotency_conflict"):
        repository.record(**{**command, "action": "rejected"})
    with pytest.raises(ContractRevisionReviewError, match="candidate_stale"):
        repository.record(**{**command, "expected_digest": "sha256:" + "a" * 64})
    with pytest.raises(ContractRevisionReviewError, match="workspace_not_found"):
        repository.latest_decisions(owner_identity_id=owner, workspace_id=unrelated.workspace_id)
    with pytest.raises(ContractRevisionReviewError, match="review_forbidden"):
        repository.record(
            **{
                **command,
                "owner_identity_id": read_only,
                "idempotency_key": "read-only-revision-review-001",
            }
        )
