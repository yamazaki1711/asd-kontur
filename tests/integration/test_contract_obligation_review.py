"""Disposable PostgreSQL acceptance of source-bound contract-duty review."""

from __future__ import annotations

from pathlib import Path

import pytest
import sqlalchemy as sa

from asd_kontur.application_spine.auth import OwnerAuthService
from asd_kontur.application_spine.config import SessionProfile, SpineSettings
from asd_kontur.support.contract_handover import contract_obligation_handover
from asd_kontur.support.contract_obligation_review import (
    ContractObligationReviewError,
    ContractObligationReviewRepository,
)

from .conftest import PostgreSQLEnvironment
from .test_ai_vlm_harness import _seed_source
from .test_workspace_lifecycle import create_tenant

pytestmark = pytest.mark.postgres


def test_review_is_scoped_idempotent_and_stale_safe(
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
        audit_pepper="synthetic-contract-review-pepper",
    )
    owner = OwnerAuthService(postgres_environment.application_engine, settings).bootstrap_owner(
        username="changed-contract-review-owner",
        password="Changed-Contract-Review-Password-42!",
        display_name="Changed contract review owner",
    )
    read_only = OwnerAuthService(postgres_environment.application_engine, settings).bootstrap_owner(
        username="changed-contract-read-only",
        password="Changed-Contract-Read-Only-Password-42!",
        display_name="Changed contract read-only owner",
    )
    with postgres_environment.owner_engine.begin() as connection:
        connection.execute(
            sa.text(
                "INSERT INTO application.owner_organization_grants VALUES "
                "(:owner,:organization,ARRAY['workspace.read','support.review'],1,CURRENT_TIMESTAMP)"
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
    candidate = contract_obligation_handover(
        {
            "clauses": [
                {
                    "clause_id": "changed-clause-1",
                    "clause_key": "3.7",
                    "source_version_id": str(source_id),
                    "source_locator_id": str(locator_id),
                    "source_text": "The Contractor gives notice before concealed work.",
                    "contractor_obligation": "Give notice before concealed work.",
                }
            ]
        },
        workspace_id=tenant.workspace_id,
    )[0]
    reviews = ContractObligationReviewRepository(postgres_environment.application_engine)
    command = {
        "owner_identity_id": owner,
        "workspace_id": tenant.workspace_id,
        "candidate": candidate,
        "expected_digest": candidate["candidate_digest"],
        "action": "confirmed",
        "reason": "Checked against source clause 3.7.",
        "idempotency_key": "changed-review-request-001",
    }
    first = reviews.record(**command)
    repeated = reviews.record(**command)
    assert first["review_state"] == "confirmed"
    assert first["idempotent_replay"] is False
    assert repeated["idempotent_replay"] is True
    assert (
        len(reviews.latest_decisions(owner_identity_id=owner, workspace_id=tenant.workspace_id))
        == 1
    )
    with pytest.raises(ContractObligationReviewError, match="idempotency_conflict"):
        reviews.record(**{**command, "action": "rejected"})
    with pytest.raises(ContractObligationReviewError, match="candidate_stale"):
        reviews.record(**{**command, "expected_digest": "sha256:" + "a" * 64})
    with pytest.raises(ContractObligationReviewError, match="workspace_not_found"):
        reviews.latest_decisions(owner_identity_id=owner, workspace_id=unrelated.workspace_id)
    with pytest.raises(ContractObligationReviewError, match="review_forbidden"):
        reviews.record(
            **{
                **command,
                "owner_identity_id": read_only,
                "idempotency_key": "read-only-review-denied-001",
            }
        )
