"""Materialize the qualified synthetic Support product path in a durable demo database.

This command is deployment-only.  It reuses the same asserted fixture that backs the
live Product Spine E2E, then verifies the canonical package/finalization denominator
before publishing a receipt.  It never reads or imports an actual OKS workspace.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path

import sqlalchemy as sa
from sqlalchemy.engine import make_url

REPOSITORY = Path(__file__).resolve().parents[1]
if str(REPOSITORY) not in sys.path:
    sys.path.insert(0, str(REPOSITORY))

from run_product_spine_e2e_server import _seed_support_production_path  # noqa: E402,I001


EXPECTED_HEAD = "0029_pilot_usable_e2e"
DEMO_OWNER_ID = "owner:" + hashlib.sha256(b"synthetic-product-owner").hexdigest()[:24]


def _required(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"{name} is required")
    return value


def _current_workspace(engine: sa.Engine) -> str | None:
    with engine.connect() as connection:
        value = connection.scalar(
            sa.text(
                "SELECT w.workspace_id FROM workspace.workspaces w JOIN "
                "application.owner_organization_grants g ON g.organization_id=w.organization_id "
                "WHERE g.owner_identity_id=:owner AND w.lifecycle_state='ACTIVE' AND EXISTS "
                "(SELECT 1 FROM workspace.support_finalized_document_versions f WHERE "
                "f.organization_id=w.organization_id AND f.workspace_id=w.workspace_id) "
                "ORDER BY w.created_at LIMIT 1"
            ),
            {"owner": DEMO_OWNER_ID},
        )
    return str(value) if value is not None else None


def _verify(engine: sa.Engine, workspace_id: str, object_root: Path) -> dict[str, object]:
    queries = {
        "package_versions": "workspace.id_package_versions",
        "volume_book_versions": "workspace.id_package_volume_book_versions",
        "register_versions": "workspace.support_register_candidates",
        "finalized_documents": "workspace.support_finalized_document_versions",
    }
    with engine.connect() as connection:
        organization_id = connection.scalar(
            sa.text("SELECT organization_id FROM workspace.workspaces WHERE workspace_id=:w"),
            {"w": workspace_id},
        )
        if organization_id is None:
            raise RuntimeError("synthetic demo workspace not found after seed")
        counts = {
            name: int(
                connection.scalar(
                    sa.text(
                        f"SELECT count(*) FROM {table} WHERE organization_id=:o AND workspace_id=:w"
                    ),
                    {"o": organization_id, "w": workspace_id},
                )
                or 0
            )
            for name, table in queries.items()
        }
        finalized = (
            connection.execute(
                sa.text(
                    "SELECT f.finalized_document_id,c.bytes_digest,c.object_reference,"
                    "c.generation_run_id "
                    "FROM workspace.support_finalized_document_versions f JOIN "
                    "workspace.support_generated_document_candidates c ON "
                    "c.organization_id=f.organization_id AND c.workspace_id=f.workspace_id AND "
                    "c.generated_candidate_id=f.generated_candidate_id WHERE f.organization_id=:o "
                    "AND f.workspace_id=:w ORDER BY f.finalized_at DESC LIMIT 1"
                ),
                {"o": organization_id, "w": workspace_id},
            )
            .mappings()
            .one()
        )
        counts["field_resolutions"] = int(
            connection.scalar(
                sa.text(
                    "SELECT count(*) FROM workspace.support_generation_field_resolutions WHERE "
                    "organization_id=:o AND workspace_id=:w AND generation_run_id=:run"
                ),
                {"o": organization_id, "w": workspace_id, "run": finalized["generation_run_id"]},
            )
            or 0
        )
        readiness = (
            connection.execute(
                sa.text(
                    "SELECT required_count,finalized_count,missing_count,blocked_count,status FROM "
                    "workspace.id_package_readiness_evaluations WHERE organization_id=:o AND "
                    "workspace_id=:w ORDER BY evaluated_at DESC LIMIT 1"
                ),
                {"o": organization_id, "w": workspace_id},
            )
            .mappings()
            .one()
        )
    expected = {
        "package_versions": 4,
        "volume_book_versions": 4,
        "register_versions": 4,
        "finalized_documents": 1,
        "field_resolutions": 28,
    }
    if counts != expected:
        raise RuntimeError(f"synthetic demo denominator mismatch: {counts!r}")
    readiness_payload = {key: readiness[key] for key in readiness.keys()}
    if readiness_payload != {
        "required_count": 4,
        "finalized_count": 1,
        "missing_count": 2,
        "blocked_count": 1,
        "status": "incomplete",
    }:
        raise RuntimeError(f"synthetic demo readiness mismatch: {readiness_payload!r}")
    object_path = (object_root / str(finalized["object_reference"])).resolve(strict=True)
    if object_root not in object_path.parents or not object_path.is_file():
        raise RuntimeError("finalized artifact object reference is invalid")
    return {
        "schema_version": "public-product-demo-receipt@1.0.0",
        "workspace_id": workspace_id,
        "organization_id": str(organization_id),
        "synthetic": True,
        "counts": counts,
        "readiness": readiness_payload,
        "finalized_document_id": str(finalized["finalized_document_id"]),
        "finalized_artifact_digest": str(finalized["bytes_digest"]),
        "finalized_artifact_size_bytes": object_path.stat().st_size,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()
    if not args.receipt.is_absolute():
        raise RuntimeError("receipt path must be absolute")
    database_url = make_url(_required("ASD_DATABASE_URL"))
    if database_url.get_backend_name() != "postgresql":
        raise RuntimeError("ASD_DATABASE_URL must use PostgreSQL")
    object_root = Path(_required("ASD_OBJECT_STORE_ROOT")).resolve()
    object_root.mkdir(parents=True, exist_ok=True)
    engine = sa.create_engine(database_url, pool_pre_ping=True)
    try:
        with engine.connect() as connection:
            head = connection.scalar(sa.text("SELECT version_num FROM alembic_version"))
        if head != EXPECTED_HEAD:
            raise RuntimeError(f"migration head mismatch: {head!r}")
        workspace_id = _current_workspace(engine)
        reused = workspace_id is not None
        if workspace_id is None:
            with tempfile.TemporaryDirectory(prefix="asd-public-demo-seed-") as temporary:
                workspace_id = _seed_support_production_path(
                    database_url=database_url,
                    runtime_root=Path(temporary),
                    object_store_root=object_root,
                )
        receipt = _verify(engine, workspace_id, object_root)
        receipt["outcome"] = "existing_verified" if reused else "materialized_verified"
        receipt["recorded_at"] = datetime.now(UTC).isoformat()
        args.receipt.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        payload = json.dumps(receipt, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
        args.receipt.write_text(payload, encoding="utf-8")
        args.receipt.chmod(0o600)
        print(json.dumps(receipt, ensure_ascii=False, sort_keys=True))
    finally:
        engine.dispose()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
