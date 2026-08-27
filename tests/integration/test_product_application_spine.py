from __future__ import annotations

import io
from pathlib import Path
from typing import Any, cast

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
from pypdf import PdfWriter

from asd_kontur.application_spine.config import SessionProfile, SpineSettings
from asd_kontur.application_spine.models import JobState
from asd_kontur.application_spine.object_store import WorkspaceObjectStore
from asd_kontur.application_spine.postgres import (
    SpinePersistenceError,
    SpinePostgresRepository,
)
from asd_kontur.application_spine.worker import DocumentWorker
from asd_kontur.web_app import create_app

from .conftest import PostgreSQLEnvironment

pytestmark = pytest.mark.postgres


def _database_url(engine: sa.Engine) -> str:
    return engine.url.render_as_string(hide_password=False)


def _settings(environment: PostgreSQLEnvironment, root: Path) -> SpineSettings:
    objects = root / "objects"
    archives = root / "archives"
    objects.mkdir()
    archives.mkdir()
    return SpineSettings(
        database_url=_database_url(environment.application_engine),
        lifecycle_database_url=_database_url(environment.lifecycle_engine),
        worker_database_url=_database_url(environment.document_worker_engine),
        destruction_database_url=_database_url(environment.destruction_engine),
        object_store_root=objects,
        archive_store_root=archives,
        session_profile=SessionProfile.DEVELOPMENT_LOOPBACK,
        audit_pepper="synthetic-product-spine-audit-pepper",
        max_file_bytes=4 * 1024 * 1024,
        max_batch_bytes=8 * 1024 * 1024,
    )


def _pdf(page_count: int = 2) -> bytes:
    target = io.BytesIO()
    writer = PdfWriter()
    for _ in range(page_count):
        writer.add_blank_page(width=595, height=842)
    writer.write(target)
    return target.getvalue()


def _login(client: TestClient, username: str, password: str) -> dict[str, Any]:
    response = client.post(
        "/api/v1/session/login",
        json={"username": username, "password": password},
    )
    assert response.status_code == 200
    return cast(dict[str, Any], response.json())


def _csrf(client: TestClient) -> dict[str, str]:
    value = client.cookies.get("asd_csrf")
    assert value
    return {"X-CSRF-Token": value}


def test_spine_browser_contract_jobs_evidence_and_reset_isolation(
    postgres_environment: PostgreSQLEnvironment,
    tmp_path: Path,
) -> None:
    settings = _settings(postgres_environment, tmp_path)
    app = create_app(engine=postgres_environment.application_engine, settings=settings)
    app.state.container.auth.bootstrap_owner(
        username="spine-owner",
        password="Synthetic-Owner-Password-42!",
        display_name="Synthetic owner",
    )
    with TestClient(app) as client:
        assert client.get("/api/v1/session").status_code == 401
        _login(client, "spine-owner", "Synthetic-Owner-Password-42!")
        csrf = _csrf(client)
        workspace_a = client.post(
            "/api/v1/workspaces",
            json={"display_name": "Synthetic workspace A"},
            headers=csrf,
        ).json()
        workspace_b = client.post(
            "/api/v1/workspaces",
            json={"display_name": "Synthetic workspace B"},
            headers=csrf,
        ).json()
        assert workspace_a["lifecycle_state"] == "ACTIVE"
        upload = client.post(
            f"/api/v1/workspaces/{workspace_a['workspace_id']}/documents",
            files=[("files", ("two-pages.pdf", _pdf(), "text/plain"))],
            headers=csrf,
        )
        assert upload.status_code == 202, upload.text
        assert len(upload.json()["accepted_document_ids"]) == 1

        worker_repository = SpinePostgresRepository(postgres_environment.document_worker_engine)
        interrupted = worker_repository.claim_next_job(
            worker_identity="synthetic-interrupted-worker",
            lease_seconds=5,
        )
        assert interrupted is not None
        worker_repository.mark_job_running(
            interrupted,
            worker_identity="synthetic-interrupted-worker",
        )
        with postgres_environment.owner_engine.begin() as connection:
            connection.execute(
                sa.text(
                    "UPDATE workspace.durable_jobs SET lease_expires_at=CURRENT_TIMESTAMP - "
                    "interval '1 second' WHERE job_id=:job"
                ),
                {"job": interrupted.job_id},
            )
        restarted_worker = DocumentWorker(
            worker_repository,
            WorkspaceObjectStore(
                settings.object_store_root,
                chunk_bytes=settings.upload_chunk_bytes,
                max_file_bytes=settings.max_file_bytes,
            ),
            worker_identity="synthetic-restarted-worker",
            lease_seconds=5,
        )
        recovered = restarted_worker.run_once()
        assert recovered is not None
        assert str(recovered.job_id) == str(interrupted.job_id)
        with pytest.raises(SpinePersistenceError, match="job_lease_fence_rejected"):
            worker_repository.mark_job_running(
                interrupted,
                worker_identity="synthetic-interrupted-worker",
            )
        outcomes = [recovered]
        while outcome := restarted_worker.run_once():
            outcomes.append(outcome)
        # The interrupted lease is recovered first; every job that the worker can
        # execute before the deterministic classification failure must succeed.
        # The exact count is asserted from the durable job ledger below instead of
        # from this scheduling-local list.
        assert outcomes[:-1]
        assert all(value.state is JobState.SUCCEEDED for value in outcomes[:-1])
        assert outcomes[-1].state is JobState.FAILED
        assert outcomes[-1].outcome_code == "classification_evidence_unavailable"
        duplicate = client.post(
            f"/api/v1/workspaces/{workspace_a['workspace_id']}/documents",
            files=[("files", ("two-pages.pdf", _pdf(), "application/pdf"))],
            headers=csrf,
        )
        assert duplicate.status_code == 202
        assert duplicate.json() == upload.json()
        jobs = client.get(f"/api/v1/workspaces/{workspace_a['workspace_id']}/jobs").json()
        assert len(jobs) == 17
        assert sum(value["state"] == "succeeded" for value in jobs) == 9
        assert sum(value["state"] == "failed" for value in jobs) == 1
        assert sum(value["state"] == "reconciliation_required" for value in jobs) == 7
        documents = client.get(f"/api/v1/workspaces/{workspace_a['workspace_id']}/documents").json()
        assert len(documents["items"]) == 1
        document = documents["items"][0]
        assert document["version"] == 1
        assert document["prior_versions"] == []
        assert document["job_ids"] == upload.json()["job_ids"]
        assert document["page_count"] == 2
        assert document["capability_gaps"] == ["OCR_REQUIRED"]
        evidence = client.get(
            f"/api/v1/workspaces/{workspace_a['workspace_id']}/evidence/"
            f"{document['document_id']}/pages/2"
        )
        assert evidence.status_code == 200
        assert evidence.json()["locator"]["page_number"] == 2
        assert evidence.json()["locator"]["region"] == [0.0, 0.0, 1.0, 1.0]
        for mode in ("Tender", "Support", "Audit", "Restoration"):
            mode_response = client.get(
                f"/api/v1/workspaces/{workspace_a['workspace_id']}/modes/{mode}"
            )
            assert mode_response.status_code == 200
            assert mode_response.json()["readiness"] == "FOUNDATION_ONLY"
            assert mode_response.json()["gaps"]
        knowledge_before = client.get("/api/v1/platform/knowledge-status").json()
        with postgres_environment.owner_engine.connect() as connection:
            qualification_status = connection.scalar(
                sa.text(
                    "SELECT status FROM platform.platform_memory_qualification_decisions "
                    "ORDER BY recorded_at DESC,version DESC LIMIT 1"
                )
            )
        assert knowledge_before["memory_data_defect"] is (qualification_status != "pass")
        assert knowledge_before["knowledge_ready"] is False
        ntd_seed_before = client.get("/api/v1/platform/ntd-seed-status").json()
        assert ntd_seed_before["counts"]["denominator"] == 25
        assert ntd_seed_before["counts"]["registered_identity_count"] == 0
        assert ntd_seed_before["complete"] is False

        prepared = client.post(
            f"/api/v1/workspaces/{workspace_a['workspace_id']}/lifecycle/reset/prepare",
            json={"confirmation": "PREPARE_WORKSPACE_RESET"},
            headers=csrf,
        )
        assert prepared.status_code == 200, prepared.text
        challenge = prepared.json()
        executed = client.post(
            f"/api/v1/workspaces/{workspace_a['workspace_id']}/lifecycle/reset/execute",
            json={
                "challenge_id": challenge["challenge_id"],
                "confirmation_text": challenge["confirmation_text"],
            },
            headers=csrf,
        )
        assert executed.status_code == 200, executed.text
        receipt = executed.json()
        assert receipt["outcome"] == "verified"
        assert receipt["platform_fingerprint_before"] == receipt["platform_fingerprint_after"]
        remaining = client.get("/api/v1/workspaces").json()
        assert [value["workspace_id"] for value in remaining] == [workspace_b["workspace_id"]]
        assert client.get("/api/v1/platform/knowledge-status").json() == knowledge_before
        assert client.get("/api/v1/platform/ntd-seed-status").json() == ntd_seed_before
        assert any(settings.archive_store_root.rglob("*.zip"))
        assert client.post("/api/v1/session/logout", headers=csrf).status_code == 204
        assert client.get("/api/v1/workspaces").status_code == 401

    with postgres_environment.owner_engine.connect() as connection:
        state = connection.scalar(
            sa.text(
                "SELECT lifecycle_state FROM workspace.workspaces WHERE workspace_id=:workspace"
            ),
            {"workspace": workspace_a["workspace_id"]},
        )
        assert state == "DESTROYED"
        assert (
            connection.scalar(
                sa.text(
                    "SELECT count(*) FROM application.workspace_reset_terminal_receipts "
                    "WHERE workspace_id=:workspace AND outcome='verified'"
                ),
                {"workspace": workspace_a["workspace_id"]},
            )
            == 1
        )


def test_job_cancellation_and_retry_exhaustion_are_terminal_and_receipted(
    postgres_environment: PostgreSQLEnvironment,
    tmp_path: Path,
) -> None:
    settings = _settings(postgres_environment, tmp_path)
    app = create_app(engine=postgres_environment.application_engine, settings=settings)
    app.state.container.auth.bootstrap_owner(
        username="spine-cancellation-owner",
        password="Synthetic-Cancellation-Password-42!",
        display_name="Synthetic cancellation owner",
    )
    with TestClient(app) as client:
        for _ in range(settings.login_max_attempts):
            assert (
                client.post(
                    "/api/v1/session/login",
                    json={"username": "unknown-owner", "password": "Invalid-Password-42!"},
                ).status_code
                == 401
            )
        assert (
            client.post(
                "/api/v1/session/login",
                json={"username": "unknown-owner", "password": "Invalid-Password-42!"},
            ).status_code
            == 429
        )
        login_response = client.post(
            "/api/v1/session/login",
            json={
                "username": "spine-cancellation-owner",
                "password": "Synthetic-Cancellation-Password-42!",
            },
        )
        assert login_response.status_code == 200
        session_cookie = next(
            value
            for value in login_response.headers.get_list("set-cookie")
            if value.startswith("asd_session=")
        )
        assert "HttpOnly" in session_cookie
        assert "SameSite=strict" in session_cookie
        assert "Secure" not in session_cookie
        csrf = _csrf(client)
        assert (
            client.post(
                "/api/v1/workspaces",
                json={"display_name": "Missing CSRF workspace"},
            ).status_code
            == 401
        )
        assert client.post("/api/v1/session/rotate", headers=csrf).status_code == 200
        csrf = _csrf(client)
        workspace = client.post(
            "/api/v1/workspaces",
            json={"display_name": "Synthetic cancellation workspace"},
            headers=csrf,
        ).json()
        first = client.post(
            f"/api/v1/workspaces/{workspace['workspace_id']}/documents",
            files=[("files", ("cancel-before-effect.pdf", _pdf(), "application/pdf"))],
            headers=csrf,
        ).json()
        queued_job = first["job_ids"][0]
        cancelled = client.post(
            f"/api/v1/workspaces/{workspace['workspace_id']}/jobs/{queued_job}/cancel",
            json={"confirmation": "CANCEL_JOB"},
            headers=csrf,
        )
        assert cancelled.status_code == 202

        second = client.post(
            f"/api/v1/workspaces/{workspace['workspace_id']}/documents",
            files=[("files", ("cancel-after-crash.pdf", _pdf(3), "application/pdf"))],
            headers=csrf,
        ).json()
        worker_repository = SpinePostgresRepository(postgres_environment.document_worker_engine)
        running = worker_repository.claim_next_job(
            worker_identity="synthetic-cancellation-worker",
            lease_seconds=5,
        )
        assert running is not None
        assert str(running.job_id) == second["job_ids"][0]
        worker_repository.mark_job_running(
            running,
            worker_identity="synthetic-cancellation-worker",
        )
        assert (
            client.post(
                f"/api/v1/workspaces/{workspace['workspace_id']}/jobs/{running.job_id}/cancel",
                json={"confirmation": "CANCEL_JOB"},
                headers=csrf,
            ).status_code
            == 202
        )
        with postgres_environment.owner_engine.begin() as connection:
            connection.execute(
                sa.text(
                    "UPDATE workspace.durable_jobs SET lease_expires_at=CURRENT_TIMESTAMP - "
                    "interval '1 second' WHERE job_id=:job"
                ),
                {"job": running.job_id},
            )
        assert worker_repository.reconcile_unclaimable_jobs() >= 1

        third = client.post(
            f"/api/v1/workspaces/{workspace['workspace_id']}/documents",
            files=[("files", ("retry-exhaustion.pdf", _pdf(4), "application/pdf"))],
            headers=csrf,
        ).json()
        retry_job = third["job_ids"][0]
        with postgres_environment.owner_engine.begin() as connection:
            object_key = str(
                connection.scalar(
                    sa.text(
                        "SELECT input_manifest->>'object_key' FROM workspace.durable_jobs "
                        "WHERE job_id=:job"
                    ),
                    {"job": retry_job},
                )
            )
            connection.execute(
                sa.text("UPDATE workspace.durable_jobs SET max_attempts=1 WHERE job_id=:job"),
                {"job": retry_job},
            )
        app.state.container.object_store.delete(object_key)
        worker = DocumentWorker(
            worker_repository,
            app.state.container.object_store,
            worker_identity="synthetic-retry-worker",
            lease_seconds=5,
        )
        retry_outcome = worker.run_once()
        assert retry_outcome is not None
        assert retry_outcome.state is JobState.RECONCILIATION_REQUIRED
        assert retry_outcome.outcome_code == "retry_exhausted"

        jobs = client.get(f"/api/v1/workspaces/{workspace['workspace_id']}/jobs").json()
        by_id = {item["job_id"]: item for item in jobs}
        assert by_id[queued_job]["state"] == "cancelled"
        assert by_id[queued_job]["terminal_receipt_id"] is not None
        assert by_id[str(running.job_id)]["state"] == "cancelled"
        assert by_id[str(running.job_id)]["terminal_receipt_id"] is not None
        assert by_id[retry_job]["state"] == "reconciliation_required"
        assert by_id[retry_job]["terminal_receipt_id"] is not None
