from __future__ import annotations

import io
import json
import os
import resource
import sys
import time
from pathlib import Path
from uuid import uuid4

import pytest
import sqlalchemy as sa

from asd_kontur.application_spine.auth import OwnerAuthService
from asd_kontur.application_spine.config import SessionProfile, SpineSettings
from asd_kontur.application_spine.object_store import WorkspaceObjectStore
from asd_kontur.application_spine.postgres import SpinePostgresRepository
from asd_kontur.application_spine.services import ProductSpineService, UploadPart
from asd_kontur.application_spine.worker import DocumentWorker
from asd_kontur.lifecycle import PostgresLifecycleRepository

from .conftest import PostgreSQLEnvironment

pytestmark = pytest.mark.postgres


def _database_url(engine: sa.Engine) -> str:
    return engine.url.render_as_string(hide_password=False)


def _profile_count() -> int:
    value = int(os.environ.get("ASD_SPINE_SCALE_FILES", "100"))
    if value not in {100, 1000, 5000, 10000}:
        raise ValueError("ASD_SPINE_SCALE_FILES must be one of 100, 1000, 5000, 10000")
    return value


def test_spine_content_minimal_scale_profile(
    postgres_environment: PostgreSQLEnvironment,
    tmp_path: Path,
) -> None:
    file_count = _profile_count()
    object_root = tmp_path / "objects"
    archive_root = tmp_path / "archives"
    object_root.mkdir()
    archive_root.mkdir()
    settings = SpineSettings(
        database_url=_database_url(postgres_environment.application_engine),
        lifecycle_database_url=_database_url(postgres_environment.lifecycle_engine),
        worker_database_url=_database_url(postgres_environment.document_worker_engine),
        destruction_database_url=_database_url(postgres_environment.destruction_engine),
        object_store_root=object_root,
        archive_store_root=archive_root,
        session_profile=SessionProfile.DEVELOPMENT_LOOPBACK,
        audit_pepper="synthetic-scale-profile-audit-pepper",
        max_file_bytes=1024 * 1024,
        max_batch_bytes=64 * 1024 * 1024,
        max_batch_files=1000,
    )
    object_store = WorkspaceObjectStore(
        object_root,
        chunk_bytes=settings.upload_chunk_bytes,
        max_file_bytes=settings.max_file_bytes,
    )
    application_repository = SpinePostgresRepository(postgres_environment.application_engine)
    service = ProductSpineService(
        application_repository,
        PostgresLifecycleRepository(postgres_environment.lifecycle_engine),
        object_store,
        settings,
    )
    owner = OwnerAuthService(postgres_environment.application_engine, settings).bootstrap_owner(
        username=f"scale-owner-{file_count}",
        password="Synthetic-Scale-Owner-Password-42!",
        display_name=f"Synthetic scale owner {file_count}",
    )
    workspace = service.create_workspace(
        owner_identity_id=owner,
        display_name=f"Synthetic scale qualification {file_count}",
        correlation_id=uuid4(),
    )

    started = time.perf_counter()
    accepted = 0
    rejected = 0
    enqueued = 0
    for batch_start in range(0, file_count, 1000):
        batch_count = min(1000, file_count - batch_start)
        parts = tuple(
            UploadPart(
                ordinal=index + 1,
                original_name=f"synthetic-{batch_start + index:05d}.txt",
                relative_path=f"qualification/{batch_start + index:05d}.txt",
                client_media_type="text/plain",
                client_size_bytes=None,
                client_digest=None,
                stream=io.BytesIO(
                    f"ASD-KONTUR synthetic scale record {batch_start + index}\n".encode()
                ),
            )
            for index in range(batch_count)
        )
        result = service.register_uploads(
            owner_identity_id=owner,
            workspace_id=workspace.workspace_id,
            parts=parts,
            correlation_id=uuid4(),
        )
        accepted += len(result.accepted_document_ids)
        rejected += result.rejected_count
        enqueued += len(result.job_ids)
    admission_seconds = time.perf_counter() - started

    assert accepted == file_count
    assert rejected == 0
    assert enqueued == file_count * 17

    first_page_started = time.perf_counter()
    page, cursor = service.list_documents(
        owner_identity_id=owner,
        workspace_id=workspace.workspace_id,
        limit=100,
        cursor=None,
        media_type=None,
        status=None,
        sort="recorded_asc",
    )
    first_page_seconds = time.perf_counter() - first_page_started
    observed_ids = {item.document_id for item in page}
    while cursor is not None:
        page, cursor = service.list_documents(
            owner_identity_id=owner,
            workspace_id=workspace.workspace_id,
            limit=100,
            cursor=cursor,
            media_type=None,
            status=None,
            sort="recorded_asc",
        )
        observed_ids.update(item.document_id for item in page)
    assert len(observed_ids) == file_count

    worker_one = DocumentWorker(
        SpinePostgresRepository(postgres_environment.document_worker_engine),
        object_store,
        worker_identity=f"scale-worker-one-{file_count}",
        lease_seconds=5,
    )
    worker_two = DocumentWorker(
        SpinePostgresRepository(postgres_environment.document_worker_engine),
        object_store,
        worker_identity=f"scale-worker-two-{file_count}",
        lease_seconds=5,
    )
    assert worker_one.run_once() is not None
    assert worker_two.run_once() is not None

    with postgres_environment.owner_engine.connect() as connection:
        state_rows = dict(
            connection.execute(
                sa.text(
                    "SELECT state,count(*) FROM workspace.durable_jobs "
                    "WHERE workspace_id=:workspace GROUP BY state"
                ),
                {"workspace": workspace.workspace_id},
            ).all()
        )
        document_rows = int(
            connection.scalar(
                sa.text(
                    "SELECT count(*) FROM workspace.document_records WHERE workspace_id=:workspace"
                ),
                {"workspace": workspace.workspace_id},
            )
            or 0
        )
    assert document_rows == file_count
    assert sum(int(value) for value in state_rows.values()) == file_count * 17
    assert int(state_rows.get("succeeded", 0)) == 2
    assert int(state_rows.get("queued", 0)) == file_count * 17 - 2

    max_resident_raw = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    max_resident_bytes = (
        int(max_resident_raw) if sys.platform == "darwin" else int(max_resident_raw) * 1024
    )
    receipt = {
        "profile": f"synthetic-content-minimal-{file_count}",
        "file_count": file_count,
        "accepted_count": accepted,
        "rejected_count": rejected,
        "durable_job_count": enqueued,
        "post_restart_state_counts": dict(sorted(state_rows.items())),
        "registry_identity_count": len(observed_ids),
        "admission_seconds": round(admission_seconds, 6),
        "first_registry_page_seconds": round(first_page_seconds, 6),
        "max_resident_bytes": max_resident_bytes,
        "threshold_status": "UNSET_MEASURED_ONLY",
        "fixture": "synthetic_content_minimal_no_project_data",
    }
    receipt_path = os.environ.get("ASD_SPINE_SCALE_RECEIPT")
    if receipt_path:
        destination = Path(receipt_path)
        if not destination.is_absolute():
            raise ValueError("ASD_SPINE_SCALE_RECEIPT must be outside Git at an absolute path")
        destination.write_text(json.dumps(receipt, sort_keys=True, indent=2) + "\n")
