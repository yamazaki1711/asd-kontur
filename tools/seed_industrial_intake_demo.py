"""Materialize the anonymized industrial-intake corpus in the public demo workspace."""

from __future__ import annotations

import argparse
import json
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

import sqlalchemy as sa
from build_industrial_intake_synthetic_corpus import build
from seed_public_product_demo import DEMO_OWNER_ID, EXPECTED_HEAD, _current_workspace

from asd_kontur.application_spine.config import SpineSettings
from asd_kontur.application_spine.object_store import WorkspaceObjectStore
from asd_kontur.application_spine.postgres import SpinePostgresRepository
from asd_kontur.application_spine.services import ProductSpineService, UploadPart
from asd_kontur.application_spine.worker import DocumentWorker
from asd_kontur.lifecycle import PostgresLifecycleRepository

PREFIX = "industrial-intake-synthetic-v1"


def _json_default(value: object) -> str:
    return str(value)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--receipt", required=True, type=Path)
    args = parser.parse_args()
    if not args.receipt.is_absolute():
        raise RuntimeError("receipt path must be absolute")
    settings = SpineSettings.from_env()
    application_engine = sa.create_engine(settings.database_url, pool_pre_ping=True)
    lifecycle_engine = sa.create_engine(settings.lifecycle_database_url, pool_pre_ping=True)
    worker_engine = sa.create_engine(settings.worker_database_url, pool_pre_ping=True)
    try:
        with application_engine.connect() as connection:
            head = connection.scalar(sa.text("SELECT version_num FROM alembic_version"))
        if head != EXPECTED_HEAD:
            raise RuntimeError(f"migration head mismatch: {head!r}")
        workspace_raw = _current_workspace(application_engine)
        if workspace_raw is None:
            raise RuntimeError("qualified public demo workspace is unavailable")
        workspace_id = UUID(workspace_raw)
        store = WorkspaceObjectStore(
            settings.object_store_root,
            chunk_bytes=settings.upload_chunk_bytes,
            max_file_bytes=settings.max_file_bytes,
        )
        repository = SpinePostgresRepository(application_engine)
        service = ProductSpineService(
            repository,
            PostgresLifecycleRepository(lifecycle_engine),
            store,
            settings,
        )
        with tempfile.TemporaryDirectory(prefix="asd-industrial-intake-demo-") as temporary:
            corpus_root = Path(temporary) / "corpus"
            manifest = build(corpus_root)
            paths = [
                path
                for path in sorted(corpus_root.rglob("*"))
                if path.is_file() and path.name != "corpus-manifest.json"
            ]
            handles = [path.open("rb") for path in paths]
            try:
                registration = service.register_uploads(
                    owner_identity_id=DEMO_OWNER_ID,
                    workspace_id=workspace_id,
                    parts=tuple(
                        UploadPart(
                            ordinal=index,
                            original_name=path.name,
                            relative_path=(f"{PREFIX}/{path.relative_to(corpus_root).as_posix()}"),
                            client_media_type="application/octet-stream",
                            client_size_bytes=path.stat().st_size,
                            client_digest=None,
                            stream=handle,
                        )
                        for index, (path, handle) in enumerate(zip(paths, handles, strict=True), 1)
                    ),
                    correlation_id=uuid4(),
                )
            finally:
                for handle in handles:
                    handle.close()

        worker = DocumentWorker(
            SpinePostgresRepository(worker_engine),
            store,
            worker_identity="deployment-industrial-intake-seed",
            lease_seconds=settings.job_lease_seconds,
        )
        outcomes = []
        for _ in range(3000):
            outcome = worker.run_once()
            if outcome is None:
                break
            outcomes.append(outcome)
        else:
            raise RuntimeError("industrial intake seed queue did not reach a stable state")

        view = service.project_understanding(
            owner_identity_id=DEMO_OWNER_ID,
            workspace_id=workspace_id,
        )
        if not view or not view["work_packages"]:
            raise RuntimeError("industrial intake seed did not produce a project model")
        with application_engine.connect() as connection:
            prior_reviews = int(
                connection.scalar(
                    sa.text(
                        "SELECT count(*) FROM workspace.project_candidate_review_decisions "
                        "WHERE workspace_id=:workspace AND "
                        "reason LIKE 'Демонстрационная проверка:%'"
                    ),
                    {"workspace": workspace_id},
                )
                or 0
            )
        if prior_reviews == 0:
            field = view["candidates"]["project_fields"][0]
            quantity = view["candidates"]["quantities"][0]
            service.review_project_candidate(
                owner_identity_id=DEMO_OWNER_ID,
                workspace_id=workspace_id,
                candidate_kind="project_field",
                candidate_id=UUID(str(field["candidate_id"])),
                candidate_version=int(field["version"]),
                action="confirmed",
                resolved_value=None,
                reason="Демонстрационная проверка: подтверждено по исходному фрагменту",
            )
            service.review_project_candidate(
                owner_identity_id=DEMO_OWNER_ID,
                workspace_id=workspace_id,
                candidate_kind="quantity",
                candidate_id=UUID(str(quantity["candidate_id"])),
                candidate_version=int(quantity["version"]),
                action="corrected",
                resolved_value=str(quantity["normalized_value"] or quantity["value"]),
                reason="Демонстрационная проверка: значение приведено по ведомости объёмов",
            )
            service.start_project_understanding(
                owner_identity_id=DEMO_OWNER_ID,
                workspace_id=workspace_id,
                correlation_id=uuid4(),
            )
            while worker.run_once() is not None:
                pass
            view = service.project_understanding(
                owner_identity_id=DEMO_OWNER_ID,
                workspace_id=workspace_id,
            )
            assert view is not None

        with application_engine.connect() as connection:
            counts = {
                "documents": int(
                    connection.scalar(
                        sa.text(
                            "SELECT count(*) FROM workspace.document_versions "
                            "WHERE workspace_id=:w "
                            "AND sanitized_relative_path LIKE :prefix"
                        ),
                        {"w": workspace_id, "prefix": f"{PREFIX}/%"},
                    )
                    or 0
                ),
                "archive_members": int(
                    connection.scalar(
                        sa.text(
                            "SELECT count(*) FROM workspace.intake_archive_members "
                            "WHERE workspace_id=:w"
                        ),
                        {"w": workspace_id},
                    )
                    or 0
                ),
                "review_decisions": int(
                    connection.scalar(
                        sa.text(
                            "SELECT count(*) FROM workspace.project_candidate_review_decisions "
                            "WHERE workspace_id=:w AND reason LIKE 'Демонстрационная проверка:%'"
                        ),
                        {"w": workspace_id},
                    )
                    or 0
                ),
            }
        if counts["documents"] != 14 or counts["archive_members"] != 2:
            raise RuntimeError(f"industrial intake demo denominator mismatch: {counts!r}")
        receipt = {
            "schema_version": "industrial-intake-demo-seed@1.0.0",
            "workspace_id": str(workspace_id),
            "synthetic": True,
            "contains_real_oks_data": False,
            "corpus_version": manifest["corpus_version"],
            "corpus_fingerprint": manifest["logical_fingerprint"],
            "registration": {
                "accepted": len(registration.accepted_document_ids),
                "duplicates": len(registration.duplicate_document_ids),
                "rejected": registration.rejected_count,
            },
            "counts": {
                **counts,
                "work_packages": len(view["work_packages"]),
                "matrix_rows": len(view["matrix"]["matrix"]["rows"]),
                "project_fields": len(view["candidates"]["project_fields"]),
                "quantities": len(view["candidates"]["quantities"]),
                "materials": len(view["candidates"]["materials"]),
                "defects": len(view["defects"]),
            },
            "worker_outcomes": {
                state: sum(item.state.value == state for item in outcomes)
                for state in sorted({item.state.value for item in outcomes})
            },
            "recorded_at": datetime.now(UTC).isoformat(),
        }
        args.receipt.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        args.receipt.write_text(
            json.dumps(receipt, ensure_ascii=False, sort_keys=True, indent=2, default=_json_default)
            + "\n",
            encoding="utf-8",
        )
        args.receipt.chmod(0o600)
        print(json.dumps(receipt, ensure_ascii=False, sort_keys=True, default=_json_default))
    finally:
        worker_engine.dispose()
        lifecycle_engine.dispose()
        application_engine.dispose()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
