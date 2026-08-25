"""Run a disposable PostgreSQL-backed Product Spine for browser E2E only."""

from __future__ import annotations

import json
import os
import shutil
import tempfile
from argparse import Namespace
from pathlib import Path

import sqlalchemy as sa
import uvicorn
from alembic import command
from alembic.config import Config
from sqlalchemy.engine import URL, make_url

from asd_kontur.application_spine.auth import OwnerAuthService
from asd_kontur.application_spine.config import SessionProfile, SpineSettings
from asd_kontur.web_app import create_app


def _required(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"{name} is required")
    return value


def _migrate(repository: Path, database_url: URL) -> None:
    configuration = Config(str(repository / "alembic.ini"))
    configuration.cmd_opts = Namespace(
        x=[f"database_url={database_url.render_as_string(hide_password=False)}"]
    )
    command.upgrade(configuration, "head")


def main() -> None:
    repository = Path(__file__).resolve().parents[1]
    base_url = make_url(_required("ASD_TEST_DATABASE_URL"))
    if base_url.get_backend_name() != "postgresql":
        raise RuntimeError("ASD_TEST_DATABASE_URL must use PostgreSQL")
    state_path = Path(_required("ASD_E2E_STATE_PATH"))
    if not state_path.is_absolute():
        raise RuntimeError("ASD_E2E_STATE_PATH must be absolute")
    suffix = str(os.getpid())
    database_name = f"asd_spine_e2e_{suffix}"
    roles = {
        "application": f"asd_spine_e2e_app_{suffix}",
        "worker": f"asd_spine_e2e_worker_{suffix}",
        "lifecycle": f"asd_spine_e2e_lifecycle_{suffix}",
        "destruction": f"asd_spine_e2e_destruction_{suffix}",
    }
    password = "synthetic-e2e-process-only"
    cluster_url = base_url.set(database="postgres")
    cluster = sa.create_engine(cluster_url, isolation_level="AUTOCOMMIT")
    runtime_root = Path(tempfile.mkdtemp(prefix="asd-spine-live-e2e-"))
    database_url = base_url.set(database=database_name)
    app_engine: sa.Engine | None = None
    try:
        with cluster.begin() as connection:
            connection.exec_driver_sql(f'CREATE DATABASE "{database_name}"')
        _migrate(repository, database_url)
        with cluster.begin() as connection:
            for role in roles.values():
                connection.exec_driver_sql(
                    f'CREATE ROLE "{role}" LOGIN NOSUPERUSER NOCREATEDB '
                    f"NOCREATEROLE INHERIT PASSWORD '{password}'"
                )
            connection.exec_driver_sql(f'GRANT asd_app TO "{roles["application"]}"')
            connection.exec_driver_sql(f'GRANT asd_document_worker TO "{roles["worker"]}"')
            connection.exec_driver_sql(f'GRANT asd_lifecycle_service TO "{roles["lifecycle"]}"')
            connection.exec_driver_sql(
                f'GRANT asd_destruction_executor TO "{roles["destruction"]}"'
            )
        role_urls = {
            name: database_url.set(username=role, password=password) for name, role in roles.items()
        }
        objects = runtime_root / "objects"
        archives = runtime_root / "archives"
        objects.mkdir()
        archives.mkdir()
        settings = SpineSettings(
            database_url=role_urls["application"].render_as_string(hide_password=False),
            lifecycle_database_url=role_urls["lifecycle"].render_as_string(hide_password=False),
            worker_database_url=role_urls["worker"].render_as_string(hide_password=False),
            destruction_database_url=role_urls["destruction"].render_as_string(hide_password=False),
            object_store_root=objects,
            archive_store_root=archives,
            session_profile=SessionProfile.DEVELOPMENT_LOOPBACK,
            audit_pepper="synthetic-live-browser-e2e-audit-pepper",
            bind_host="127.0.0.1",
            bind_port=int(os.environ.get("ASD_E2E_PORT", "4173")),
            job_lease_seconds=5,
            frontend_dist=repository / "frontend" / "dist",
        )
        app_engine = sa.create_engine(settings.database_url, pool_pre_ping=True)
        OwnerAuthService(app_engine, settings).bootstrap_owner(
            username="synthetic-live-owner",
            password="Synthetic-Live-Owner-Password-42!",
            display_name="Synthetic live owner",
        )
        state_path.write_text(
            json.dumps(
                {
                    "worker_database_url": settings.worker_database_url,
                    "object_store_root": str(objects),
                    "max_file_bytes": settings.max_file_bytes,
                    "upload_chunk_bytes": settings.upload_chunk_bytes,
                    "lease_seconds": settings.job_lease_seconds,
                    "database_name": database_name,
                    "roles": list(roles.values()),
                },
                sort_keys=True,
            ),
            encoding="utf-8",
        )
        state_path.chmod(0o600)
        server = uvicorn.Server(
            uvicorn.Config(
                create_app(engine=app_engine, settings=settings),
                host=settings.bind_host,
                port=settings.bind_port,
                access_log=False,
                log_level="warning",
            )
        )
        server.run()
    finally:
        if app_engine is not None:
            app_engine.dispose()
        state_path.unlink(missing_ok=True)
        with cluster.begin() as connection:
            connection.exec_driver_sql(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                f"WHERE datname='{database_name}' AND pid <> pg_backend_pid()"
            )
            connection.exec_driver_sql(f'DROP DATABASE IF EXISTS "{database_name}"')
            for role in roles.values():
                connection.exec_driver_sql(f'DROP ROLE IF EXISTS "{role}"')
        cluster.dispose()
        shutil.rmtree(runtime_root, ignore_errors=True)


if __name__ == "__main__":
    main()
