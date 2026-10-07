"""The Support preflight is isolated and immutable."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
from sqlalchemy.exc import DBAPIError

from asd_kontur.application_spine.auth import OwnerAuthService
from asd_kontur.application_spine.config import SessionProfile, SpineSettings
from asd_kontur.application_spine.models import semantic_digest
from asd_kontur.domain import uuid7
from asd_kontur.lifecycle import LifecycleState, PostgresLifecycleRepository
from asd_kontur.support.incoming_inspection import INCOMING_CHECKS, evaluate_incoming_inspection
from asd_kontur.support.incoming_inspection_postgres import (
    IncomingInspectionError,
    IncomingInspectionRepository,
)
from asd_kontur.web_app import create_app

from .conftest import PostgreSQLEnvironment
from .test_workspace_lifecycle import create_tenant, transition

pytestmark = pytest.mark.postgres


def test_incoming_inspection_rls_and_immutable(
    postgres_environment: PostgreSQLEnvironment,
) -> None:
    first = create_tenant(postgres_environment)
    second = create_tenant(postgres_environment)
    transition(
        PostgresLifecycleRepository(postgres_environment.lifecycle_engine),
        first,
        1,
        LifecycleState.ACTIVE,
        "incoming-inspection-activate",
    )
    checks = [
        {"key": key, "state": "pending", "basis": ""} for key, _label, _kind in INCOMING_CHECKS
    ]
    result = evaluate_incoming_inspection(checks)
    inspection = {"material_name": "Concrete", "batch_reference": "delivery-7", "checks": checks}
    with postgres_environment.application_engine.begin() as connection:
        connection.execute(
            sa.select(
                sa.func.set_config("asd.organization_id", str(first.organization_id), True),
                sa.func.set_config("asd.workspace_id", str(first.workspace_id), True),
            )
        )
        connection.execute(
            sa.text(
                "INSERT INTO workspace.support_incoming_inspection_preflights "
                "(organization_id,workspace_id,preflight_id,idempotency_key,material_name,"
                "batch_reference,inspection,result,payload_digest,submitted_by) VALUES "
                "(:o,:w,:id,'delivery-7','Concrete','delivery-7',CAST(:inspection AS jsonb),"
                "CAST(:result AS jsonb),:digest,'human:synthetic')"
            ),
            {
                "o": first.organization_id,
                "w": first.workspace_id,
                "id": uuid7(),
                "inspection": json.dumps(inspection),
                "result": json.dumps(result),
                "digest": semantic_digest(inspection),
            },
        )
        assert (
            connection.scalar(
                sa.text("SELECT count(*) FROM workspace.support_incoming_inspection_preflights")
            )
            == 1
        )
    with postgres_environment.application_engine.begin() as connection:
        connection.execute(
            sa.select(
                sa.func.set_config("asd.organization_id", str(second.organization_id), True),
                sa.func.set_config("asd.workspace_id", str(second.workspace_id), True),
            )
        )
        assert (
            connection.scalar(
                sa.text("SELECT count(*) FROM workspace.support_incoming_inspection_preflights")
            )
            == 0
        )
    with pytest.raises(DBAPIError):
        with postgres_environment.application_engine.begin() as connection:
            connection.execute(
                sa.select(
                    sa.func.set_config("asd.organization_id", str(first.organization_id), True),
                    sa.func.set_config("asd.workspace_id", str(first.workspace_id), True),
                )
            )
            connection.execute(
                sa.text("DELETE FROM workspace.support_incoming_inspection_preflights")
            )


def test_owner_scoped_submission_replay_and_lifecycle_fence(
    postgres_environment: PostgreSQLEnvironment, tmp_path: Path
) -> None:
    first = create_tenant(postgres_environment)
    second = create_tenant(postgres_environment)
    lifecycle = PostgresLifecycleRepository(postgres_environment.lifecycle_engine)
    transition(lifecycle, first, 1, LifecycleState.ACTIVE, "inspection-owner-active")
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
        object_store_root=tmp_path / "objects",
        archive_store_root=tmp_path / "archives",
        session_profile=SessionProfile.DEVELOPMENT_LOOPBACK,
        audit_pepper="synthetic-incoming-inspection-pepper",
    )
    settings.object_store_root.mkdir()
    settings.archive_store_root.mkdir()
    owner = OwnerAuthService(postgres_environment.application_engine, settings).bootstrap_owner(
        username="inspection-owner",
        password="Synthetic-Inspection-Password-42!",
        display_name="Inspection owner",
    )
    with postgres_environment.owner_engine.begin() as connection:
        connection.execute(
            sa.text(
                "INSERT INTO application.owner_organization_grants VALUES "
                "(:owner,:organization,ARRAY['workspace.read','workspace.write'],1,CURRENT_TIMESTAMP)"
            ),
            {"owner": owner, "organization": first.organization_id},
        )
    repository = IncomingInspectionRepository(postgres_environment.application_engine)
    checks = [
        {"key": key, "state": "pending", "basis": ""} for key, _label, _kind in INCOMING_CHECKS
    ]
    command = {
        "owner_identity_id": owner,
        "workspace_id": first.workspace_id,
        "material_name": "Reinforcement steel",
        "batch_reference": "delivery-42",
        "checks": checks,
        "idempotency_key": "inspection-delivery-42",
    }
    first_record = repository.submit(**command)
    replay = repository.submit(**command)
    assert first_record["preflight_id"] == replay["preflight_id"]
    assert first_record["result"]["outcome"] == "incomplete"
    assert len(repository.list(owner_identity_id=owner, workspace_id=first.workspace_id)) == 1
    with pytest.raises(IncomingInspectionError, match="idempotency_conflict"):
        repository.submit(**{**command, "material_name": "Structural steel"})
    with pytest.raises(IncomingInspectionError, match="workspace_not_found"):
        repository.list(owner_identity_id=owner, workspace_id=second.workspace_id)
    app = create_app(engine=postgres_environment.application_engine, settings=settings)
    with TestClient(app) as client:
        login = client.post(
            "/api/v1/session/login",
            json={
                "username": "inspection-owner",
                "password": "Synthetic-Inspection-Password-42!",
            },
        )
        assert login.status_code == 200
        csrf = client.cookies.get("asd_csrf")
        assert csrf
        response = client.post(
            f"/api/v1/workspaces/{first.workspace_id}/support/incoming-inspections",
            json={
                "material_name": "Reinforcement steel",
                "batch_reference": "delivery-42",
                "checks": checks,
                "idempotency_key": "inspection-delivery-42-api",
            },
            headers={"X-CSRF-Token": csrf},
        )
        assert response.status_code == 201
        assert response.json()["result"]["hold_for_use"] is True
        listing = client.get(
            f"/api/v1/workspaces/{first.workspace_id}/support/incoming-inspections"
        )
        assert listing.status_code == 200
        assert len(listing.json()) == 2
        register = client.get(
            f"/api/v1/workspaces/{first.workspace_id}/support/incoming-inspections/register.csv"
        )
        assert register.status_code == 200
        assert register.content.startswith(b"\xef\xbb\xbf")
        assert register.text.count("Материал не допущен") == 16
        assert "Reinforcement steel" in register.text
        denied_register = client.get(
            f"/api/v1/workspaces/{second.workspace_id}/support/"
            "incoming-inspections/register.csv"
        )
        assert denied_register.status_code in {403, 404}
    transition(lifecycle, first, 2, LifecycleState.FREEZING, "inspection-owner-freeze")
    with pytest.raises(IncomingInspectionError, match="support_workspace_not_active"):
        repository.submit(**{**command, "idempotency_key": "inspection-delivery-42-after-freeze"})
