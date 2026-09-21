from __future__ import annotations

import io
import json
from decimal import Decimal
from pathlib import Path
from typing import Any, cast
from uuid import UUID, uuid4

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
from pypdf import PdfWriter

from asd_kontur.application_spine.config import SessionProfile, SpineSettings
from asd_kontur.application_spine.models import ClaimedJob, JobKind, JobState, semantic_digest
from asd_kontur.application_spine.object_store import WorkspaceObjectStore
from asd_kontur.application_spine.postgres import (
    SpinePersistenceError,
    SpinePostgresRepository,
)
from asd_kontur.application_spine.worker import DocumentWorker
from asd_kontur.document_understanding.models import StructureIdentityCandidate
from asd_kontur.document_understanding.postgres import IndustrialUnderstandingRepository
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
        release_commit="1" * 40,
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
        # A higher-priority job from another workspace must remain invisible to
        # a worker configured with the requested workspace scope.  The durable
        # claim function is SECURITY DEFINER, so this proves the explicit scope
        # predicate rather than relying on ordinary RLS filtering.
        with postgres_environment.owner_engine.begin() as connection:
            owner = connection.scalar(
                sa.text(
                    "SELECT created_by_identity_id FROM workspace.workspaces "
                    "WHERE workspace_id=:workspace"
                ),
                {"workspace": workspace_b["workspace_id"]},
            )
            foreign_manifest = {"synthetic": "foreign-workspace-job"}
            connection.execute(
                sa.text(
                    "INSERT INTO workspace.durable_jobs "
                    "(organization_id,workspace_id,job_id,job_kind,input_manifest,input_digest,"
                    "idempotency_key,state,priority,max_attempts,"
                    "retry_policy_version,provenance,correlation_id,created_by_identity_id) VALUES "
                    "(:organization,:workspace,:job,'PROJECT_DEFINITION_EXTRACTION',"
                    "CAST(:manifest AS jsonb),:digest,:key,'queued',999,1,'synthetic',"
                    "CAST(:provenance AS jsonb),:correlation,:owner)"
                ),
                {
                    "organization": workspace_b["organization_id"],
                    "workspace": workspace_b["workspace_id"],
                    "job": uuid4(),
                    "manifest": json.dumps(foreign_manifest),
                    "digest": semantic_digest(foreign_manifest),
                    "key": "synthetic-foreign-workspace-job",
                    "provenance": json.dumps({"contract": "synthetic"}),
                    "correlation": uuid4(),
                    "owner": owner,
                },
            )

        worker_repository = SpinePostgresRepository(postgres_environment.document_worker_engine)
        interrupted = worker_repository.claim_next_job(
            worker_identity="synthetic-interrupted-worker",
            lease_seconds=5,
            organization_id=UUID(workspace_a["organization_id"]),
            workspace_id=UUID(workspace_a["workspace_id"]),
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
            organization_id=UUID(workspace_a["organization_id"]),
            workspace_id=UUID(workspace_a["workspace_id"]),
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
        assert all(value.state is JobState.SUCCEEDED for value in outcomes[:-1]), [
            (value.job_id, value.state.value, value.outcome_code) for value in outcomes
        ]
        assert outcomes[-1].state is JobState.FAILED
        assert outcomes[-1].outcome_code in {
            "classification_evidence_unavailable",
            "pdf_renderer_unavailable",
            "ocr_adapters_exhausted:none_available",
        }
        duplicate = client.post(
            f"/api/v1/workspaces/{workspace_a['workspace_id']}/documents",
            files=[("files", ("two-pages.pdf", _pdf(), "application/pdf"))],
            headers=csrf,
        )
        assert duplicate.status_code == 202
        assert duplicate.json() == upload.json()
        jobs = client.get(f"/api/v1/workspaces/{workspace_a['workspace_id']}/jobs").json()
        # The upload schedules the complete current industrial-understanding
        # graph, including the work/quantity/material extraction stage.  Keep
        # this explicit rather than treating the historical 17-job topology as
        # a browser contract.
        assert len(jobs) == 18
        succeeded_count = len(outcomes) - 1
        assert sum(value["state"] == "succeeded" for value in jobs) == succeeded_count
        assert sum(value["state"] == "failed" for value in jobs) == 1
        # The failed classification stage remains distinguishable from the
        # independently queued downstream work; a page failure must not be
        # reported as a completed project analysis.
        assert sum(value["state"] == "reconciliation_required" for value in jobs) == 0
        failed_job = next(value for value in jobs if value["state"] == "failed")
        assert failed_job["typed_failure_code"] == outcomes[-1].outcome_code
        job_states = {value["job_kind"]: value["state"] for value in jobs}
        for required_success in (
            "DOCUMENT_ADMISSION",
            "DOCUMENT_HASH",
            "PDF_INVENTORY",
            "NATIVE_TEXT_EXTRACTION",
        ):
            assert job_states[required_success] == "succeeded"
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
        trial_criteria = {
            "owner_ui_path": True,
            "four_mode_results": True,
            "exact_source_navigation": True,
            "unconfirmed_facts_are_marked": True,
            "required_documents_not_fabricated": True,
            "restart_survival": True,
            "workspace_isolation": True,
            "exports_available": True,
            "limitations_visible": True,
            "rollback_available": True,
            "external_e2e_exact_commit": True,
        }
        thresholds = {
            "max_corpus_files": 250,
            "max_corpus_bytes": 1073741824,
            "admission_seconds": 180,
            "first_result_seconds": 600,
            "main_screen_seconds": 2,
            "transient_retry_rate_percent": 5,
            "unexpected_failure_rate_percent": 1,
            "interruption_recovery_seconds": 60,
        }
        decision = client.post(
            "/api/v1/admin/trial-readiness",
            json={
                "criteria": trial_criteria,
                "pilot_thresholds": thresholds,
                "external_receipts": [{"kind": "synthetic_external_e2e", "passed": True}],
                "user_blockers": [],
                "rollback_target": "sha256:synthetic-rollback-checkpoint",
            },
            headers=csrf,
        )
        assert decision.status_code == 201, decision.text
        assert decision.json()["status"] == "trial_ready"
        assert decision.json()["deployed_commit"] == "1" * 40
        assert client.get("/api/v1/admin/trial-readiness").json() == decision.json()
        capabilities = client.get("/api/v1/capabilities").json()
        assert capabilities["trial_ready"] is True
        assert capabilities["oks_ready"] is False
        assert capabilities["product_ready"] is False
        assert capabilities["blockers"] == []
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
            organization_id=UUID(workspace["organization_id"]),
            workspace_id=UUID(workspace["workspace_id"]),
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
            organization_id=UUID(workspace["organization_id"]),
            workspace_id=UUID(workspace["workspace_id"]),
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


def test_dependency_terminal_stage_recovers_only_from_matching_successor(
    postgres_environment: PostgreSQLEnvironment,
    tmp_path: Path,
) -> None:
    settings = _settings(postgres_environment, tmp_path)
    app = create_app(engine=postgres_environment.application_engine, settings=settings)
    app.state.container.auth.bootstrap_owner(
        username="dependency-owner",
        password="Synthetic-Owner-Password-42!",
        display_name="Dependency owner",
    )
    repository = SpinePostgresRepository(postgres_environment.document_worker_engine)
    application_repository = SpinePostgresRepository(postgres_environment.application_engine)
    worker = "dependency-recovery-worker"
    with TestClient(app) as client:
        _login(client, "dependency-owner", "Synthetic-Owner-Password-42!")
        csrf = _csrf(client)
        workspace = client.post(
            "/api/v1/workspaces",
            json={"display_name": "Dependency recovery"},
            headers=csrf,
        ).json()
        workspace_id = workspace["workspace_id"]
        client.post(
            f"/api/v1/workspaces/{workspace_id}/documents",
            files=[("files", ("recovery.pdf", _pdf(), "application/pdf"))],
            headers=csrf,
        ).raise_for_status()

        scope = {
            "organization_id": UUID(workspace["organization_id"]),
            "workspace_id": UUID(workspace_id),
        }
        admission = repository.claim_next_job(worker_identity=worker, lease_seconds=5, **scope)
        assert admission is not None
        repository.mark_job_running(admission, worker_identity=worker)
        repository.finish_job(
            admission,
            terminal_state=JobState.SUCCEEDED,
            outcome_code="synthetic_admission_complete",
            result_manifest={"synthetic": True},
            worker_identity=worker,
        )
        original_hash = repository.claim_next_job(worker_identity=worker, lease_seconds=5, **scope)
        assert original_hash is not None
        assert original_hash.job_kind.value == "DOCUMENT_HASH"
        repository.mark_job_running(original_hash, worker_identity=worker)
        repository.finish_job(
            original_hash,
            terminal_state=JobState.FAILED,
            outcome_code="synthetic_hash_failure",
            result_manifest={"synthetic": True},
            worker_identity=worker,
        )
        assert repository.reconcile_unclaimable_jobs() >= 1

        with postgres_environment.owner_engine.connect() as connection:
            owner = str(
                connection.scalar(
                    sa.text(
                        "SELECT created_by_identity_id FROM workspace.workspaces "
                        "WHERE workspace_id=:workspace"
                    ),
                    {"workspace": workspace_id},
                )
            )
        retry = application_repository.manually_retry_job(
            owner_identity_id=owner,
            workspace_id=UUID(workspace_id),
            job_id=original_hash.job_id,
        )
        recovered_hash = repository.claim_next_job(worker_identity=worker, lease_seconds=5, **scope)
        assert recovered_hash is not None
        assert recovered_hash.job_id == retry.job_id
        repository.mark_job_running(recovered_hash, worker_identity=worker)
        repository.finish_job(
            recovered_hash,
            terminal_state=JobState.SUCCEEDED,
            outcome_code="synthetic_hash_recovered",
            result_manifest={"synthetic": True},
            worker_identity=worker,
        )

        # Success-driven recovery advances one lineage and rewires the failed
        # prerequisite to the accepted successor. Repeating the callback must
        # not create a parallel replacement of the same blocked job.
        assert repository.recover_dependents_from_success(recovered_hash) == 1
        assert repository.recover_dependents_from_success(recovered_hash) == 0
        recovered_inventory = repository.claim_next_job(
            worker_identity=worker, lease_seconds=5, **scope
        )
        assert recovered_inventory is not None
        assert recovered_inventory.job_kind.value == "PDF_INVENTORY"
        repository.mark_job_running(recovered_inventory, worker_identity=worker)
        repository.finish_job(
            recovered_inventory,
            terminal_state=JobState.SUCCEEDED,
            outcome_code="synthetic_inventory_recovered",
            result_manifest={"synthetic": True},
            worker_identity=worker,
        )

        with postgres_environment.owner_engine.connect() as connection:
            provenance = connection.scalar(
                sa.text("SELECT provenance FROM workspace.durable_jobs WHERE job_id=:job"),
                {"job": recovered_inventory.job_id},
            )
            dependencies = connection.scalars(
                sa.text(
                    "SELECT depends_on_job_id FROM workspace.durable_job_dependencies "
                    "WHERE job_id=:job"
                ),
                {"job": recovered_inventory.job_id},
            ).all()
        assert provenance["dependency_recovery_of"]
        assert provenance["dependency_recovery_replacement"] == str(recovered_hash.job_id)
        assert dependencies == [recovered_hash.job_id]


def test_effective_jobs_keep_running_retry_visible_beyond_history_window(
    postgres_environment: PostgreSQLEnvironment,
    tmp_path: Path,
) -> None:
    """The jobs page must not hide a replacement behind old immutable attempts."""
    settings = _settings(postgres_environment, tmp_path)
    app = create_app(engine=postgres_environment.application_engine, settings=settings)
    app.state.container.auth.bootstrap_owner(
        username="effective-jobs-owner",
        password="Synthetic-Owner-Password-42!",
        display_name="Effective jobs owner",
    )
    with TestClient(app) as client:
        _login(client, "effective-jobs-owner", "Synthetic-Owner-Password-42!")
        workspace = client.post(
            "/api/v1/workspaces",
            json={"display_name": "Effective jobs workspace"},
            headers=_csrf(client),
        ).json()
        workspace_id = UUID(workspace["workspace_id"])
        organization_id = UUID(workspace["organization_id"])
        with postgres_environment.owner_engine.begin() as connection:
            owner = str(
                connection.scalar(
                    sa.text(
                        "SELECT created_by_identity_id FROM workspace.workspaces "
                        "WHERE workspace_id=:workspace"
                    ),
                    {"workspace": workspace_id},
                )
            )
            connection.execute(
                sa.select(
                    sa.func.set_config("asd.organization_id", str(organization_id), True),
                    sa.func.set_config("asd.workspace_id", str(workspace_id), True),
                )
            )
            for ordinal in range(205):
                manifest = {"synthetic": ordinal}
                connection.execute(
                    sa.text(
                        "INSERT INTO workspace.durable_jobs (organization_id,workspace_id,job_id,"
                        "job_kind,input_manifest,input_digest,idempotency_key,state,priority,"
                        "max_attempts,retry_policy_version,provenance,correlation_id,"
                        "created_by_identity_id) VALUES (:organization,:workspace,:job,"
                        "'PROJECT_DEFINITION_EXTRACTION',CAST(:manifest AS jsonb),:digest,:key,"
                        "'queued',1,1,'synthetic',CAST(:provenance AS jsonb),:correlation,:owner)"
                    ),
                    {
                        "organization": organization_id,
                        "workspace": workspace_id,
                        "job": uuid4(),
                        "manifest": json.dumps(manifest),
                        "digest": semantic_digest(manifest),
                        "key": f"synthetic-history-{ordinal}",
                        "provenance": json.dumps({"contract": "synthetic"}),
                        "correlation": uuid4(),
                        "owner": owner,
                    },
                )
            failed_job = uuid4()
            stale_lease_job = uuid4()
            shared = {"synthetic": "retry-lineage"}
            for job_id, priority, manifest in (
                (failed_job, 99, shared),
                (stale_lease_job, 98, {"synthetic": "expired-lease"}),
            ):
                connection.execute(
                    sa.text(
                        "INSERT INTO workspace.durable_jobs (organization_id,workspace_id,job_id,"
                        "job_kind,input_manifest,input_digest,idempotency_key,state,priority,"
                        "max_attempts,retry_policy_version,provenance,correlation_id,"
                        "created_by_identity_id) VALUES "
                        "(:organization,:workspace,:job,"
                        "'PROJECT_DEFINITION_EXTRACTION',CAST(:manifest AS jsonb),:digest,:key,"
                        "'queued',:priority,3,'synthetic',CAST(:provenance AS jsonb),:correlation,"
                        ":owner)"
                    ),
                    {
                        "organization": organization_id,
                        "workspace": workspace_id,
                        "job": job_id,
                        "manifest": json.dumps(manifest),
                        "digest": semantic_digest(manifest),
                        "key": f"synthetic-retry-{job_id}",
                        "priority": priority,
                        "provenance": json.dumps({"contract": "synthetic"}),
                        "correlation": uuid4(),
                        "owner": owner,
                    },
                )
        worker_repository = SpinePostgresRepository(postgres_environment.document_worker_engine)
        failed_claim = worker_repository.claim_next_job(
            worker_identity="synthetic-retry-worker",
            lease_seconds=600,
            organization_id=organization_id,
            workspace_id=workspace_id,
        )
        assert failed_claim is not None
        assert failed_claim.job_id == failed_job
        worker_repository.mark_job_running(failed_claim, worker_identity="synthetic-retry-worker")
        worker_repository.finish_job(
            failed_claim,
            terminal_state=JobState.FAILED,
            outcome_code="synthetic_terminal_failure",
            result_manifest={"semantic_effect": False},
            worker_identity="synthetic-retry-worker",
        )
        application_repository = SpinePostgresRepository(postgres_environment.application_engine)
        replacement = application_repository.manually_retry_job(
            owner_identity_id=owner, workspace_id=workspace_id, job_id=failed_job
        )
        replacement_job = replacement.job_id
        replacement_claim = worker_repository.claim_next_job(
            worker_identity="synthetic-retry-worker",
            lease_seconds=600,
            organization_id=organization_id,
            workspace_id=workspace_id,
        )
        assert replacement_claim is not None
        assert replacement_claim.job_id == replacement_job
        worker_repository.mark_job_running(
            replacement_claim, worker_identity="synthetic-retry-worker"
        )
        worker_repository.report_progress(
            replacement_claim,
            current=7,
            total=10,
            safe_message_code="engineering_semantic_batch_accepted",
        )
        stale_claim = worker_repository.claim_next_job(
            worker_identity="synthetic-retry-worker",
            lease_seconds=600,
            organization_id=organization_id,
            workspace_id=workspace_id,
        )
        assert stale_claim is not None
        assert stale_claim.job_id == stale_lease_job
        worker_repository.mark_job_running(stale_claim, worker_identity="synthetic-retry-worker")
        with postgres_environment.owner_engine.begin() as connection:
            connection.execute(
                sa.text(
                    "UPDATE workspace.durable_jobs SET lease_expires_at=CURRENT_TIMESTAMP - "
                    "interval '1 minute' WHERE organization_id=:organization "
                    "AND workspace_id=:workspace AND job_id=:job"
                ),
                {
                    "organization": organization_id,
                    "workspace": workspace_id,
                    "job": stale_lease_job,
                },
            )
        response = client.get(f"/api/v1/workspaces/{workspace_id}/jobs?effective_only=true")
        assert response.status_code == 200, response.text
        jobs = response.json()
        job_ids = {item["job_id"] for item in jobs}
        assert str(replacement_job) in job_ids
        assert str(failed_job) not in job_ids
        replacement = next(item for item in jobs if item["job_id"] == str(replacement_job))
        assert replacement["state"] == "running"
        assert replacement["progress_current"] == 7
        assert replacement["progress_total"] == 10
        assert replacement["progress_message_code"] == "engineering_semantic_batch_accepted"
        assert replacement["lease_expired"] is False
        stale = next(item for item in jobs if item["job_id"] == str(stale_lease_job))
        assert stale["state"] == "running"
        assert stale["lease_expired"] is True


def test_start_project_understanding_queues_native_semantic_recovery_once(
    postgres_environment: PostgreSQLEnvironment,
    tmp_path: Path,
) -> None:
    """A failed OCR/classification chain cannot hide usable native project text."""
    settings = _settings(postgres_environment, tmp_path)
    app = create_app(engine=postgres_environment.application_engine, settings=settings)
    app.state.container.auth.bootstrap_owner(
        username="semantic-recovery-owner",
        password="Synthetic-Owner-Password-42!",
        display_name="Semantic recovery owner",
    )
    with TestClient(app) as client:
        _login(client, "semantic-recovery-owner", "Synthetic-Owner-Password-42!")
        csrf = _csrf(client)
        workspace = client.post(
            "/api/v1/workspaces",
            json={"display_name": "Native semantic recovery"},
            headers=csrf,
        ).json()
        workspace_id = UUID(workspace["workspace_id"])
        upload = client.post(
            f"/api/v1/workspaces/{workspace_id}/documents",
            files=[
                (
                    "files",
                    (
                        "project.txt",
                        b"\xd0\x9a\xd0\xbe\xd1\x82\xd0\xbb\xd0\xbe\xd0\xb2\xd0\xb0\xd0\xbd 1",
                        "text/plain",
                    ),
                )
            ],
            headers=csrf,
        )
        assert upload.status_code == 202, upload.text

        with postgres_environment.owner_engine.begin() as connection:
            source = (
                connection.execute(
                    sa.text(
                        "SELECT document_id,version,source_version_id "
                        "FROM workspace.document_versions "
                        "WHERE organization_id=:organization AND workspace_id=:workspace"
                    ),
                    {
                        "organization": workspace["organization_id"],
                        "workspace": workspace["workspace_id"],
                    },
                )
                .mappings()
                .one()
            )
            locator_id = uuid4()
            connection.execute(
                sa.text(
                    "INSERT INTO workspace.source_locators "
                    "(organization_id,workspace_id,source_locator_id,source_version_id,"
                    "locator_kind,locator_key,locator_value,fragment_digest) VALUES "
                    "(:organization,:workspace,:locator,:source,'document_page_region','synthetic',"
                    "CAST(:value AS jsonb),:digest)"
                ),
                {
                    "organization": workspace["organization_id"],
                    "workspace": workspace["workspace_id"],
                    "locator": locator_id,
                    "source": source["source_version_id"],
                    "value": json.dumps({"page": 1, "region": [0, 0, 1, 1]}),
                    "digest": semantic_digest({"synthetic": "native-layout"}),
                },
            )
            connection.execute(
                sa.text(
                    "INSERT INTO workspace.native_layout_element_versions "
                    "(organization_id,workspace_id,element_id,version,document_id,document_version,"
                    "source_version_id,source_locator_id,page_number,element_kind,raw_text,"
                    "normalized_text,reading_order,region,cell_locator,row_index,column_index,"
                    "evidence_digest,extraction_method,profile_version,semantic_digest) VALUES "
                    "(:organization,:workspace,:element,1,:document,:version,:source,:locator,1,"
                    "'paragraph','Котлован 1','котлован 1',1,CAST(:region AS jsonb),NULL,NULL,NULL,"
                    ":evidence,'native_layout','native-layout-v0.1',:digest)"
                ),
                {
                    "organization": workspace["organization_id"],
                    "workspace": workspace["workspace_id"],
                    "element": uuid4(),
                    "document": source["document_id"],
                    "version": source["version"],
                    "source": source["source_version_id"],
                    "locator": locator_id,
                    "region": json.dumps([0, 0, 1, 1]),
                    "evidence": semantic_digest({"synthetic": "native-layout"}),
                    "digest": semantic_digest({"synthetic": "native-layout-element"}),
                },
            )
            connection.execute(
                sa.text(
                    "INSERT INTO workspace.document_role_decisions "
                    "(organization_id,workspace_id,decision_id,decision_version,document_id,"
                    "document_version,scope,selected_roles,candidate_ids,decision_code,"
                    "validator_version,source_locator_ids,decision_digest) VALUES "
                    "(:organization,:workspace,:decision,1,:document,:version,'page:1',"
                    "CAST(:roles AS text[]),CAST(:candidates AS uuid[]),'synthetic_role',"
                    "'synthetic-role-v1',ARRAY[:locator]::uuid[],:digest)"
                ),
                {
                    "organization": workspace["organization_id"],
                    "workspace": workspace["workspace_id"],
                    "decision": uuid4(),
                    "document": source["document_id"],
                    "version": source["version"],
                    "roles": ["drawing_or_scheme"],
                    "candidates": [],
                    "locator": locator_id,
                    "digest": semantic_digest({"synthetic": "drawing-role"}),
                },
            )
            connection.execute(
                sa.text(
                    "UPDATE workspace.durable_jobs SET state='paused' "
                    "WHERE organization_id=:organization AND workspace_id=:workspace "
                    "AND job_kind='PROJECT_DEFINITION_EXTRACTION'"
                ),
                {
                    "organization": workspace["organization_id"],
                    "workspace": workspace["workspace_id"],
                },
            )

        endpoint = f"/api/v1/workspaces/{workspace_id}/project-understanding/runs"
        assert client.post(endpoint, headers=csrf).status_code == 202
        assert client.post(endpoint, headers=csrf).status_code == 202
        with postgres_environment.owner_engine.connect() as connection:
            rows = (
                connection.execute(
                    sa.text(
                        "SELECT job_id,priority,provenance FROM workspace.durable_jobs WHERE "
                        "organization_id=:organization AND workspace_id=:workspace "
                        "AND job_kind='PROJECT_DEFINITION_EXTRACTION' AND "
                        "provenance->>'engineering_semantic_profile'='qwen-engineering-extraction-v15'"
                    ),
                    {
                        "organization": workspace["organization_id"],
                        "workspace": workspace["workspace_id"],
                    },
                )
                .mappings()
                .all()
            )
        assert len(rows) == 1
        assert rows[0]["priority"] == 170
        assert rows[0]["provenance"]["semantic_recovery_of"] is None
        assert (
            rows[0]["provenance"]["candidate_persistence_profile"]
            == "qwen-engineering-extraction-v15"
        )
        with postgres_environment.owner_engine.connect() as connection:
            structure_jobs = (
                connection.execute(
                    sa.text(
                        "SELECT structure.job_id,structure.idempotency_key AS structure_key,"
                        "structure.input_manifest AS structure_manifest,"
                        "structure.provenance AS structure_provenance,"
                        "dependency.depends_on_job_id,dependency.dependency_kind,"
                        "project.idempotency_key AS project_key,"
                        "project.input_manifest AS project_manifest,"
                        "project.provenance AS project_provenance FROM "
                        "workspace.durable_jobs structure "
                        "JOIN workspace.durable_job_dependencies dependency ON "
                        "dependency.organization_id=structure.organization_id AND "
                        "dependency.workspace_id=structure.workspace_id AND "
                        "dependency.job_id=structure.job_id JOIN workspace.durable_jobs project ON "
                        "project.organization_id=dependency.organization_id AND "
                        "project.workspace_id=dependency.workspace_id AND "
                        "project.job_id=dependency.depends_on_job_id WHERE "
                        "structure.organization_id=:organization AND "
                        "structure.workspace_id=:workspace AND "
                        "structure.job_kind='PROJECT_STRUCTURE_RECONCILIATION' AND "
                        "structure.idempotency_key LIKE 'project-structure-reconciliation:%' AND "
                        "project.job_kind='PROJECT_UNDERSTANDING_RECONCILIATION'"
                    ),
                    {
                        "organization": workspace["organization_id"],
                        "workspace": workspace["workspace_id"],
                    },
                )
                .mappings()
                .all()
            )
        assert len(structure_jobs) == 1
        assert structure_jobs[0]["dependency_kind"] == "success_required"
        assert structure_jobs[0]["project_key"].startswith(
            "project-understanding:project-understanding-reconciliation-v0.3:"
        )
        assert (
            structure_jobs[0]["project_manifest"]["project_reconciliation_profile"]
            == "project-understanding-reconciliation-v0.3"
        )
        assert (
            structure_jobs[0]["project_provenance"]["project_reconciliation_profile"]
            == "project-understanding-reconciliation-v0.3"
        )
        assert "project-understanding-reconciliation-v0.3" not in structure_jobs[0]["structure_key"]
        assert (
            structure_jobs[0]["structure_manifest"]["structure_identity_result_manifest_version"]
            == "current-membership-v1"
        )
        assert (
            structure_jobs[0]["structure_provenance"]["result_manifest_version"]
            == "current-membership-v1"
        )
        structure_job_id = UUID(str(structure_jobs[0]["job_id"]))
        understanding_repository = IndustrialUnderstandingRepository(
            postgres_environment.document_worker_engine
        )
        structure_claim = ClaimedJob(
            UUID(workspace["organization_id"]),
            workspace_id,
            structure_job_id,
            JobKind.PROJECT_STRUCTURE_RECONCILIATION,
            {},
            "sha256:" + "e" * 64,
            1,
            1,
            "none",
        )
        understanding_repository.record_structure_identity_progress(
            structure_claim, completed_groups=0, total_groups=2
        )
        understanding_repository.record_structure_identity_progress(
            structure_claim, completed_groups=0, total_groups=2
        )
        with postgres_environment.owner_engine.connect() as connection:
            progress_rows = (
                connection.execute(
                    sa.text(
                        "SELECT progress_current,progress_total,safe_message_code FROM "
                        "workspace.job_progress_events WHERE organization_id=:organization AND "
                        "workspace_id=:workspace AND job_id=:job AND "
                        "event_type='engineering.structure_identity_progress'"
                    ),
                    {
                        "organization": workspace["organization_id"],
                        "workspace": workspace["workspace_id"],
                        "job": structure_job_id,
                    },
                )
                .mappings()
                .all()
            )
        assert [dict(row) for row in progress_rows] == [
            {
                "progress_current": 0,
                "progress_total": 2,
                "safe_message_code": "structure_identity_group_processed",
            }
        ]
        status_response = client.get(f"/api/v1/workspaces/{workspace_id}/project-understanding")
        assert status_response.status_code == 200, status_response.text
        structure_status = status_response.json()["structure_identity_reconciliation"]
        assert structure_status["job_id"] == str(structure_job_id)
        assert structure_status["state"] == "queued"
        assert structure_status["progress_current"] == 0
        assert structure_status["progress_total"] == 2
        assert structure_status["candidate_authority"] == "candidate_only"

        # A terminal group result is atomic with its candidate and survives a
        # new repository instance, so worker restart cannot repeat Qwen work.
        second_locator_id = uuid4()
        first_node_id = uuid4()
        second_node_id = uuid4()
        identity_candidate_id = uuid4()
        with postgres_environment.owner_engine.begin() as connection:
            connection.execute(
                sa.text(
                    "INSERT INTO workspace.source_locators "
                    "(organization_id,workspace_id,source_locator_id,source_version_id,"
                    "locator_kind,locator_key,locator_value,fragment_digest) VALUES "
                    "(:organization,:workspace,:locator,:source,'document_page_region','synthetic-2',"
                    "CAST(:value AS jsonb),:digest)"
                ),
                {
                    "organization": workspace["organization_id"],
                    "workspace": workspace["workspace_id"],
                    "locator": second_locator_id,
                    "source": source["source_version_id"],
                    "value": json.dumps({"page": 1, "region": [1, 0, 1, 1]}),
                    "digest": semantic_digest({"synthetic": "native-layout-2"}),
                },
            )
            for node_id, node_locator, suffix in (
                (first_node_id, locator_id, "left"),
                (second_node_id, second_locator_id, "right"),
            ):
                connection.execute(
                    sa.text(
                        "INSERT INTO workspace.project_structure_node_versions "
                        "(organization_id,workspace_id,structure_node_id,version,node_kind,raw_name,"
                        "normalized_name,parent_node_id,source_locator_id,status,fingerprint) "
                        "VALUES "
                        "(:organization,:workspace,:node,1,'facility',:name,'facility 1',NULL,"
                        ":locator,'candidate',:fingerprint)"
                    ),
                    {
                        "organization": workspace["organization_id"],
                        "workspace": workspace["workspace_id"],
                        "node": node_id,
                        "name": f"Facility 1 {suffix}",
                        "locator": node_locator,
                        "fingerprint": semantic_digest({"structure-node": suffix}),
                    },
                )
        identity_input_manifest = (
            {"structure_node_id": str(first_node_id)},
            {"structure_node_id": str(second_node_id)},
        )
        group_fingerprint = semantic_digest(
            {
                "profile_version": "qwen-structure-identity-v1",
                "observations": identity_input_manifest,
            }
        )
        identity_candidate = StructureIdentityCandidate(
            identity_candidate_id,
            "facility",
            "Facility 1",
            (first_node_id, second_node_id),
            (locator_id, second_locator_id),
            Decimal("0.9"),
            "qwen-structure-identity-v1",
        )
        understanding_repository.persist_structure_identity_group_outcome(
            structure_claim,
            group_fingerprint=group_fingerprint,
            profile_version="qwen-structure-identity-v1",
            input_structure_node_ids=(first_node_id, second_node_id),
            input_manifest=identity_input_manifest,
            candidates=(identity_candidate,),
        )
        receipts = IndustrialUnderstandingRepository(
            postgres_environment.document_worker_engine
        ).load_structure_identity_group_receipts(
            structure_claim, profile_version="qwen-structure-identity-v1"
        )
        assert receipts[group_fingerprint] == {
            "outcome": "accepted",
            "identity_candidate_ids": (str(identity_candidate_id),),
            "failure_code": None,
        }
        compatible_fingerprint = semantic_digest(
            {
                "profile_version": "qwen-structure-identity-v2",
                "observations": identity_input_manifest,
            }
        )
        compatible_receipts = understanding_repository.load_structure_identity_group_receipts(
            structure_claim,
            profile_version="qwen-structure-identity-v2",
            compatible_profile_versions=("qwen-structure-identity-v1",),
        )
        assert compatible_receipts[compatible_fingerprint] == receipts[group_fingerprint]
        stale_identity_candidate_id = uuid4()
        stale_input_manifest = tuple(reversed(identity_input_manifest))
        stale_group_fingerprint = semantic_digest(
            {
                "profile_version": "qwen-structure-identity-v1",
                "observations": stale_input_manifest,
            }
        )
        understanding_repository.persist_structure_identity_group_outcome(
            structure_claim,
            group_fingerprint=stale_group_fingerprint,
            profile_version="qwen-structure-identity-v1",
            input_structure_node_ids=(second_node_id, first_node_id),
            input_manifest=stale_input_manifest,
            candidates=(
                StructureIdentityCandidate(
                    stale_identity_candidate_id,
                    "facility",
                    "Stale Facility 1",
                    (second_node_id, first_node_id),
                    (second_locator_id, locator_id),
                    Decimal("0.8"),
                    "qwen-structure-identity-v1",
                ),
            ),
        )
        with postgres_environment.owner_engine.connect() as connection:
            assert (
                connection.scalar(
                    sa.text(
                        "SELECT count(*) FROM workspace.project_structure_identity_candidates "
                        "WHERE organization_id=:organization AND workspace_id=:workspace "
                        "AND identity_candidate_id=:candidate"
                    ),
                    {
                        "organization": workspace["organization_id"],
                        "workspace": workspace["workspace_id"],
                        "candidate": identity_candidate_id,
                    },
                )
                == 1
            )
        with postgres_environment.owner_engine.begin() as connection:
            connection.execute(
                sa.text(
                    "UPDATE workspace.durable_jobs SET state='running',"
                    "lease_owner='structure-filter-test-worker',lease_generation=1,"
                    "lease_expires_at=CURRENT_TIMESTAMP + interval '1 minute' "
                    "WHERE organization_id=:organization AND workspace_id=:workspace "
                    "AND job_id=:job"
                ),
                {
                    "organization": workspace["organization_id"],
                    "workspace": workspace["workspace_id"],
                    "job": structure_job_id,
                },
            )
        SpinePostgresRepository(postgres_environment.document_worker_engine).finish_job(
            structure_claim,
            terminal_state=JobState.SUCCEEDED,
            outcome_code="synthetic_structure_reconciliation_succeeded",
            result_manifest={
                "structure_identity_candidate_ids": [str(identity_candidate_id)],
                "structure_identity_group_fingerprints": [group_fingerprint],
            },
            worker_identity="structure-filter-test-worker",
        )
        filtered_view = client.get(f"/api/v1/workspaces/{workspace_id}/project-understanding")
        assert filtered_view.status_code == 200, filtered_view.text
        assert {
            candidate["identity_candidate_id"]
            for candidate in filtered_view.json()["structure_identity_candidates"]
        } == {str(identity_candidate_id)}
        application_view = client.get(
            f"/api/v1/workspaces/{workspace_id}/project-understanding?section=structure"
        )
        assert application_view.status_code == 200, application_view.text
        application_payload = application_view.json()
        assert application_payload["structure_nodes"] == []
        assert application_payload["work_packages"] == []
        assert {
            candidate["identity_candidate_id"]
            for candidate in application_payload["structure_identity_candidates"]
        } == {str(identity_candidate_id)}
        assert application_payload["summary_counts"]["structure_node_count"] == 0
        assert application_payload["summary_counts"]["structure_identity_candidate_count"] == 1

        # A later reconciliation receipt may refer to the same source, but it
        # is not itself a semantic extraction attempt.  Recovery must continue
        # from the failed semantic input rather than recursively treating that
        # receipt as the source predecessor.
        failed_semantic_job = UUID(str(rows[0]["job_id"]))
        descendant_job = uuid4()
        semantic_manifest = {
            "document_id": str(source["document_id"]),
            "document_version": int(source["version"]),
            "source_version_id": str(source["source_version_id"]),
        }
        repository = SpinePostgresRepository(postgres_environment.document_worker_engine)
        claimed = repository.claim_next_job(
            worker_identity="semantic-recovery-test-worker",
            lease_seconds=5,
            organization_id=UUID(workspace["organization_id"]),
            workspace_id=workspace_id,
        )
        assert claimed is not None
        assert claimed.job_id == failed_semantic_job
        repository.mark_job_running(claimed, worker_identity="semantic-recovery-test-worker")
        repository.finish_job(
            claimed,
            terminal_state=JobState.FAILED,
            outcome_code="synthetic_semantic_failure",
            result_manifest={"semantic_effect": False},
            worker_identity="semantic-recovery-test-worker",
        )
        with postgres_environment.owner_engine.begin() as connection:
            connection.execute(
                sa.text(
                    "INSERT INTO workspace.durable_jobs (organization_id,workspace_id,job_id,"
                    "subject_document_id,job_kind,input_manifest,input_digest,idempotency_key,state,"
                    "priority,attempt_count,max_attempts,retry_policy_version,lease_owner,"
                    "lease_generation,lease_expires_at,provenance,correlation_id,"
                    "causation_id,created_by_identity_id) "
                    "VALUES (:organization,:workspace,:job,:document,"
                    "'PROJECT_DEFINITION_EXTRACTION',CAST(:manifest AS jsonb),:digest,:key,"
                    "'leased',120,1,3,'synthetic-v1','semantic-recovery-test-worker',1,"
                    "CURRENT_TIMESTAMP + interval '1 minute',CAST(:provenance AS jsonb),"
                    ":correlation,:causation,'semantic-recovery-owner')"
                ),
                {
                    "organization": workspace["organization_id"],
                    "workspace": workspace["workspace_id"],
                    "job": descendant_job,
                    "document": source["document_id"],
                    "manifest": json.dumps(semantic_manifest),
                    "digest": semantic_digest({"kind": "synthetic", "manifest": semantic_manifest}),
                    "key": f"synthetic-reconciliation:{descendant_job}",
                    "provenance": json.dumps({"contract": "synthetic.reconciliation@1.0.0"}),
                    "correlation": uuid4(),
                    "causation": failed_semantic_job,
                },
            )

        repository.finish_job(
            ClaimedJob(
                UUID(workspace["organization_id"]),
                workspace_id,
                descendant_job,
                JobKind.PROJECT_DEFINITION_EXTRACTION,
                semantic_manifest,
                semantic_digest({"kind": "synthetic", "manifest": semantic_manifest}),
                1,
                1,
                "none",
            ),
            terminal_state=JobState.RECONCILIATION_REQUIRED,
            outcome_code="synthetic_reconciliation_required",
            result_manifest={"semantic_effect": False},
            worker_identity="semantic-recovery-test-worker",
        )

        assert client.post(endpoint, headers=csrf).status_code == 202
        assert client.post(endpoint, headers=csrf).status_code == 202
        with postgres_environment.owner_engine.connect() as connection:
            semantic_rows = (
                connection.execute(
                    sa.text(
                        "SELECT job_id,causation_id,provenance FROM workspace.durable_jobs WHERE "
                        "organization_id=:organization AND workspace_id=:workspace AND "
                        "job_kind='PROJECT_DEFINITION_EXTRACTION' AND "
                        "provenance->>'engineering_semantic_profile'="
                        "'qwen-engineering-extraction-v15' "
                        "ORDER BY created_at,job_id"
                    ),
                    {
                        "organization": workspace["organization_id"],
                        "workspace": workspace["workspace_id"],
                    },
                )
                .mappings()
                .all()
            )
        assert len(semantic_rows) == 2
        successor = semantic_rows[-1]
        assert UUID(str(successor["causation_id"])) == failed_semantic_job
        assert successor["provenance"]["semantic_recovery_of"] == str(failed_semantic_job)
        assert successor["provenance"]["semantic_recovery_reason"] == "incomplete_semantic_coverage"
        assert (
            successor["provenance"]["semantic_coverage_recovery_contract"]
            == "engineering-leaf-recovery-v6"
        )


def test_project_view_selects_only_the_latest_source_semantic_profile(
    postgres_environment: PostgreSQLEnvironment,
    tmp_path: Path,
) -> None:
    """Legacy generic observations cannot mix with a completed Qwen semantic pass."""
    settings = _settings(postgres_environment, tmp_path)
    app = create_app(engine=postgres_environment.application_engine, settings=settings)
    app.state.container.auth.bootstrap_owner(
        username="profile-scope-owner",
        password="Synthetic-Owner-Password-42!",
        display_name="Profile scope owner",
    )
    with TestClient(app) as client:
        _login(client, "profile-scope-owner", "Synthetic-Owner-Password-42!")
        csrf = _csrf(client)
        workspace = client.post(
            "/api/v1/workspaces",
            json={"display_name": "Profile-scoped candidates"},
            headers=csrf,
        ).json()
        workspace_id = UUID(workspace["workspace_id"])
        upload = client.post(
            f"/api/v1/workspaces/{workspace_id}/documents",
            files=[("files", ("project.txt", b"native project text", "text/plain"))],
            headers=csrf,
        )
        assert upload.status_code == 202, upload.text
        with postgres_environment.owner_engine.begin() as connection:
            source = (
                connection.execute(
                    sa.text(
                        "SELECT document_id,version,source_version_id FROM "
                        "workspace.document_versions "
                        "WHERE organization_id=:organization AND workspace_id=:workspace"
                    ),
                    {
                        "organization": workspace["organization_id"],
                        "workspace": workspace["workspace_id"],
                    },
                )
                .mappings()
                .one()
            )
            job_id = connection.execute(
                sa.text(
                    "SELECT job_id FROM workspace.durable_jobs WHERE organization_id=:organization "
                    "AND workspace_id=:workspace AND job_kind='PROJECT_DEFINITION_EXTRACTION' "
                    "ORDER BY created_at,job_id LIMIT 1"
                ),
                {
                    "organization": workspace["organization_id"],
                    "workspace": workspace["workspace_id"],
                },
            ).scalar_one()
            locator_id = uuid4()
            connection.execute(
                sa.text(
                    "INSERT INTO workspace.source_locators "
                    "(organization_id,workspace_id,source_locator_id,source_version_id,locator_kind,"
                    "locator_key,locator_value,fragment_digest) VALUES "
                    "(:organization,:workspace,:locator,:source,'document_page_region','profile-test',"
                    "CAST(:value AS jsonb),:digest)"
                ),
                {
                    "organization": workspace["organization_id"],
                    "workspace": workspace["workspace_id"],
                    "locator": locator_id,
                    "source": source["source_version_id"],
                    "value": json.dumps({"page": 1, "region": [0, 0, 1, 1]}),
                    "digest": semantic_digest({"test": "profile-locator"}),
                },
            )
            for candidate_id, value, profile in (
                (uuid4(), "legacy observation", "project-definition-extraction-v0.1"),
                (uuid4(), "current observation", "qwen-engineering-extraction-v15"),
            ):
                connection.execute(
                    sa.text(
                        "INSERT INTO workspace.project_field_candidates "
                        "(organization_id,workspace_id,candidate_id,version,field_key,raw_value,"
                        "normalized_value,value_type,source_version_id,source_locator_id,"
                        "extraction_method,confidence,uncertainty_codes,conflicts,status,"
                        "extraction_profile_version,candidate_digest) VALUES "
                        "(:organization,:workspace,:candidate,1,'purpose',:value,"
                        "CAST(:normalized AS jsonb),'text',:source,:locator,'synthetic',1,"
                        "'{}','{}',"
                        "'candidate',:profile,:digest)"
                    ),
                    {
                        "organization": workspace["organization_id"],
                        "workspace": workspace["workspace_id"],
                        "candidate": candidate_id,
                        "value": value,
                        "normalized": json.dumps(value),
                        "source": source["source_version_id"],
                        "locator": locator_id,
                        "profile": profile,
                        "digest": semantic_digest({"candidate": str(candidate_id)}),
                    },
                )
            stage_id = uuid4()
            output = {"profile_scope": "qwen-engineering-extraction-v15"}
            connection.execute(
                sa.text(
                    "INSERT INTO workspace.project_understanding_stage_results "
                    "(organization_id,workspace_id,stage_result_id,job_id,document_id,document_version,"
                    "source_version_id,stage_kind,profile_version,input_digest,output_manifest,"
                    "output_digest,terminal_status) VALUES "
                    "(:organization,:workspace,:result,:job,:document,:version,:source,"
                    "'PROJECT_DEFINITION_EXTRACTION','qwen-engineering-extraction-v15',:input,"
                    "CAST(:output AS jsonb),:digest,'complete')"
                ),
                {
                    "organization": workspace["organization_id"],
                    "workspace": workspace["workspace_id"],
                    "result": stage_id,
                    "job": job_id,
                    "document": source["document_id"],
                    "version": source["version"],
                    "source": source["source_version_id"],
                    "input": semantic_digest({"test": "profile-input"}),
                    "output": json.dumps(output),
                    "digest": semantic_digest(output),
                },
            )
        response = client.get(f"/api/v1/workspaces/{workspace_id}/project-understanding")
        assert response.status_code == 200, response.text
        values = response.json()["candidates"]["project_fields"]
        assert [item["value"] for item in values] == ["current observation"]
        assert values[0]["extraction_profile_version"] == "qwen-engineering-extraction-v15"


def test_completed_semantic_source_queues_one_incremental_model_refresh(
    postgres_environment: PostgreSQLEnvironment,
    tmp_path: Path,
) -> None:
    """Partial candidate evidence becomes materializable before the corpus drains."""

    settings = _settings(postgres_environment, tmp_path)
    app = create_app(engine=postgres_environment.application_engine, settings=settings)
    app.state.container.auth.bootstrap_owner(
        username="incremental-refresh-owner",
        password="Synthetic-Owner-Password-42!",
        display_name="Incremental refresh owner",
    )
    with TestClient(app) as client:
        _login(client, "incremental-refresh-owner", "Synthetic-Owner-Password-42!")
        csrf = _csrf(client)
        workspace = client.post(
            "/api/v1/workspaces",
            json={"display_name": "Incremental semantic refresh"},
            headers=csrf,
        ).json()
        workspace_id = UUID(workspace["workspace_id"])
        assert (
            client.post(
                f"/api/v1/workspaces/{workspace_id}/documents",
                files=[("files", ("project.txt", b"native project text", "text/plain"))],
                headers=csrf,
            ).status_code
            == 202
        )
        with postgres_environment.owner_engine.begin() as connection:
            source = (
                connection.execute(
                    sa.text(
                        "SELECT document_id,version,source_version_id FROM "
                        "workspace.document_versions "
                        "WHERE organization_id=:organization AND workspace_id=:workspace"
                    ),
                    {
                        "organization": workspace["organization_id"],
                        "workspace": workspace["workspace_id"],
                    },
                )
                .mappings()
                .one()
            )
            row = (
                connection.execute(
                    sa.text(
                        "SELECT job_id,subject_document_id,input_manifest,input_digest,"
                        "correlation_id,created_by_identity_id FROM workspace.durable_jobs WHERE "
                        "organization_id=:organization "
                        "AND workspace_id=:workspace AND job_kind='PROJECT_DEFINITION_EXTRACTION' "
                        "ORDER BY created_at,job_id LIMIT 1"
                    ),
                    {
                        "organization": workspace["organization_id"],
                        "workspace": workspace["workspace_id"],
                    },
                )
                .mappings()
                .one()
            )
            semantic_job_id = uuid4()
            semantic_provenance = {
                "contract": "synthetic.incremental-semantic@1.0.0",
                "engineering_semantic_profile": "qwen-engineering-extraction-v15",
            }
            connection.execute(
                sa.text(
                    "INSERT INTO workspace.durable_jobs "
                    "(organization_id,workspace_id,job_id,subject_document_id,job_kind,input_manifest,"
                    "input_digest,idempotency_key,state,priority,max_attempts,retry_policy_version,"
                    "provenance,correlation_id,created_by_identity_id) VALUES "
                    "(:organization,:workspace,:job,:document,'PROJECT_DEFINITION_EXTRACTION',"
                    "CAST(:manifest AS jsonb),:digest,:key,'queued',999,3,'synthetic',"
                    "CAST(:provenance AS jsonb),:correlation,:owner)"
                ),
                {
                    "organization": workspace["organization_id"],
                    "workspace": workspace["workspace_id"],
                    "job": semantic_job_id,
                    "document": row["subject_document_id"],
                    "manifest": json.dumps(dict(row["input_manifest"])),
                    "digest": str(row["input_digest"]),
                    "key": f"synthetic-incremental-semantic-{semantic_job_id}",
                    "provenance": json.dumps(semantic_provenance),
                    "correlation": row["correlation_id"],
                    "owner": row["created_by_identity_id"],
                },
            )
        worker_repository = SpinePostgresRepository(postgres_environment.document_worker_engine)
        claimed = worker_repository.claim_next_job(
            worker_identity="synthetic-semantic-worker",
            lease_seconds=600,
            organization_id=UUID(workspace["organization_id"]),
            workspace_id=workspace_id,
        )
        assert claimed is not None
        assert claimed.job_id == semantic_job_id
        worker_repository.mark_job_running(claimed, worker_identity="synthetic-semantic-worker")
        worker_repository.finish_job(
            claimed,
            terminal_state=JobState.SUCCEEDED,
            outcome_code="synthetic_semantic_accepted",
            result_manifest={"semantic": "accepted"},
            worker_identity="synthetic-semantic-worker",
        )
        with postgres_environment.owner_engine.begin() as connection:
            stage_output = {"semantic": "accepted"}
            connection.execute(
                sa.text(
                    "INSERT INTO workspace.project_understanding_stage_results "
                    "(organization_id,workspace_id,stage_result_id,job_id,document_id,document_version,"
                    "source_version_id,stage_kind,profile_version,input_digest,output_manifest,"
                    "output_digest,terminal_status) VALUES "
                    "(:organization,:workspace,:result,:job,:document,:version,:source,"
                    "'PROJECT_DEFINITION_EXTRACTION','qwen-engineering-extraction-v15',:input,"
                    "CAST(:output AS jsonb),:digest,'complete')"
                ),
                {
                    "organization": workspace["organization_id"],
                    "workspace": workspace["workspace_id"],
                    "result": uuid4(),
                    "job": semantic_job_id,
                    "document": source["document_id"],
                    "version": source["version"],
                    "source": source["source_version_id"],
                    "input": semantic_digest({"test": "incremental-input"}),
                    "output": json.dumps(stage_output),
                    "digest": semantic_digest(stage_output),
                },
            )
        repository = SpinePostgresRepository(postgres_environment.application_engine)
        first = repository.schedule_incremental_project_reconciliation(claimed)
        second = repository.schedule_incremental_project_reconciliation(claimed)
        assert first is not None and first == second
        with postgres_environment.owner_engine.connect() as connection:
            refresh = (
                connection.execute(
                    sa.text(
                        "SELECT priority,causation_id,provenance->>'contract' AS contract FROM "
                        "workspace.durable_jobs WHERE organization_id=:organization "
                        "AND workspace_id=:workspace "
                        "AND job_id=:job"
                    ),
                    {
                        "organization": workspace["organization_id"],
                        "workspace": workspace["workspace_id"],
                        "job": first,
                    },
                )
                .mappings()
                .one()
            )
        assert refresh["priority"] == 165
        assert refresh["causation_id"] == semantic_job_id
        assert refresh["contract"] == "project-understanding.incremental-reconciliation@1.0.0"

        structure_job_id = uuid4()
        structure_manifest = dict(row["input_manifest"])
        structure_digest = semantic_digest(
            {"structure_job_id": str(structure_job_id), "manifest": structure_manifest}
        )
        with postgres_environment.owner_engine.begin() as connection:
            connection.execute(
                sa.text(
                    "INSERT INTO workspace.durable_jobs "
                    "(organization_id,workspace_id,job_id,subject_document_id,job_kind,input_manifest,"
                    "input_digest,idempotency_key,state,priority,started_at,heartbeat_at,attempt_count,"
                    "max_attempts,retry_policy_version,lease_owner,lease_generation,lease_expires_at,"
                    "provenance,correlation_id,created_by_identity_id) VALUES "
                    "(:organization,:workspace,:job,:document,'PROJECT_STRUCTURE_RECONCILIATION',"
                    "CAST(:manifest AS jsonb),:digest,:key,'running',110,CURRENT_TIMESTAMP,"
                    "CURRENT_TIMESTAMP,1,3,'synthetic','synthetic-structure-worker',1,"
                    "CURRENT_TIMESTAMP+interval '10 minutes',CAST('{}' AS jsonb),"
                    ":correlation,:owner)"
                ),
                {
                    "organization": workspace["organization_id"],
                    "workspace": workspace["workspace_id"],
                    "job": structure_job_id,
                    "document": row["subject_document_id"],
                    "manifest": json.dumps(structure_manifest),
                    "digest": structure_digest,
                    "key": f"synthetic-structure-refresh-{structure_job_id}",
                    "correlation": row["correlation_id"],
                    "owner": row["created_by_identity_id"],
                },
            )
        structure_claim = ClaimedJob(
            UUID(workspace["organization_id"]),
            workspace_id,
            structure_job_id,
            JobKind.PROJECT_STRUCTURE_RECONCILIATION,
            structure_manifest,
            structure_digest,
            1,
            1,
            "none",
        )
        worker_repository.finish_job(
            structure_claim,
            terminal_state=JobState.SUCCEEDED,
            outcome_code="synthetic_structure_reconciliation_succeeded",
            result_manifest={
                "structure_identity_candidate_ids": [],
                "structure_identity_reconciliation": "completed",
                "structure_identity_failed_group_count": 0,
                "workspace_semantic_coverage": {"complete": True},
            },
            worker_identity="synthetic-structure-worker",
        )
        first_structure_refresh = repository.schedule_post_structure_project_reconciliation(
            structure_claim
        )
        second_structure_refresh = repository.schedule_post_structure_project_reconciliation(
            structure_claim
        )
        assert first_structure_refresh is not None
        assert first_structure_refresh == second_structure_refresh
        with postgres_environment.owner_engine.connect() as connection:
            structure_refresh = (
                connection.execute(
                    sa.text(
                        "SELECT priority,causation_id,"
                        "input_manifest->>'project_reconciliation_profile' "
                        "AS profile,input_manifest,input_digest,"
                        "provenance->>'contract' AS contract FROM "
                        "workspace.durable_jobs WHERE organization_id=:organization "
                        "AND workspace_id=:workspace AND job_id=:job"
                    ),
                    {
                        "organization": workspace["organization_id"],
                        "workspace": workspace["workspace_id"],
                        "job": first_structure_refresh,
                    },
                )
                .mappings()
                .one()
            )
        assert structure_refresh["priority"] == 165
        assert structure_refresh["causation_id"] == structure_job_id
        assert structure_refresh["profile"] == "project-understanding-reconciliation-v0.3"
        assert (
            structure_refresh["contract"]
            == "project-understanding.post-structure-reconciliation@1.0.0"
        )
        refresh_claim = ClaimedJob(
            UUID(workspace["organization_id"]),
            workspace_id,
            first_structure_refresh,
            JobKind.PROJECT_UNDERSTANDING_RECONCILIATION,
            dict(structure_refresh["input_manifest"]),
            str(structure_refresh["input_digest"]),
            0,
            0,
            "none",
        )
        understanding_repository = IndustrialUnderstandingRepository(
            postgres_environment.document_worker_engine
        )
        with understanding_repository._session(refresh_claim) as session:
            assert (
                understanding_repository._structure_reconciliation_gaps(
                    session, refresh_claim, required=True
                )
                == set()
            )
        with postgres_environment.owner_engine.connect() as connection:
            claim_definition = connection.scalar(
                sa.text(
                    "SELECT pg_get_functiondef("
                    "'workspace.claim_next_durable_job(text,integer)'::regprocedure)"
                )
            )
        assert "incremental_source_job_id" in str(claim_definition)
