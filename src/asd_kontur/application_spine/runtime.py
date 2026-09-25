"""Operational entrypoint for the local Product Application Spine."""

from __future__ import annotations

import argparse
import getpass
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from xml.sax.saxutils import escape

import sqlalchemy as sa
import uvicorn
from alembic import command
from alembic.config import Config

from asd_kontur.assistant.gateway import ProfessionalAssistantKnowledgeQuery
from asd_kontur.assistant.postgres import AssistantRepository
from asd_kontur.assistant.worker import AssistantWorker
from asd_kontur.ntd.exact_lineage import reconcile_exact_native_lineage
from asd_kontur.ntd.local_semantic import (
    LocalNtdProvisionRepository,
    LocalNtdProvisionWorker,
)

from .auth import OwnerAuthService
from .config import SpineSettings
from .object_store import WorkspaceObjectStore
from .postgres import SpinePostgresRepository
from .worker import DocumentWorker


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="asd-kontur-spine")
    subcommands = parser.add_subparsers(dest="command", required=True)
    bootstrap = subcommands.add_parser("bootstrap-owner")
    bootstrap.add_argument("--username", required=True)
    bootstrap.add_argument("--display-name", required=True)
    subcommands.add_parser("database-preflight")
    subcommands.add_parser("migrate")
    subcommands.add_parser("frontend-build")
    subcommands.add_parser("serve-api")
    worker = subcommands.add_parser("run-worker")
    worker.add_argument("--identity", default=f"document-worker:{os.getpid()}")
    assistant_worker = subcommands.add_parser("run-assistant-worker")
    assistant_worker.add_argument("--identity", default=f"assistant-worker:{os.getpid()}")
    ntd_worker = subcommands.add_parser("run-ntd-worker")
    ntd_worker.add_argument("--identity", default=f"ntd-worker:{os.getpid()}")
    ntd_enqueue = subcommands.add_parser("enqueue-ntd-provisions")
    ntd_enqueue.add_argument("--limit", type=int, default=2)
    ntd_enqueue.add_argument("--profile-cap", type=int, default=20)
    ntd_lineage = subcommands.add_parser("reconcile-ntd-native-lineage")
    ntd_lineage.add_argument("--document-limit", type=int, default=15)
    subcommands.add_parser("status")
    subcommands.add_parser("health")
    stop = subcommands.add_parser("stop")
    stop.add_argument(
        "--service", choices=("api", "worker", "assistant-worker", "qwen", "all"), default="all"
    )
    logs = subcommands.add_parser("logs")
    logs.add_argument(
        "--service", choices=("api", "worker", "assistant-worker", "qwen", "all"), default="all"
    )
    logs.add_argument("--lines", type=int, default=100)
    launchd = subcommands.add_parser("render-launchd")
    launchd.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    settings = SpineSettings.from_env()
    if args.command == "database-preflight":
        return _database_preflight(settings)
    if args.command == "migrate":
        return _migrate(settings)
    if args.command == "frontend-build":
        return _frontend_build()
    if args.command == "bootstrap-owner":
        password = getpass.getpass("Owner password: ")
        repeated = getpass.getpass("Repeat owner password: ")
        if password != repeated:
            raise SystemExit("passwords_do_not_match")
        engine = sa.create_engine(settings.database_url, pool_pre_ping=True)
        try:
            identity = OwnerAuthService(engine, settings).bootstrap_owner(
                username=args.username,
                password=password,
                display_name=args.display_name,
            )
        finally:
            engine.dispose()
        print(json.dumps({"status": "owner_available", "owner_identity_id": identity}))
        return 0
    if args.command == "serve-api":
        uvicorn.run(
            "asd_kontur.web_app.runtime:app",
            host=settings.bind_host,
            port=settings.bind_port,
            log_config=None,
            access_log=False,
        )
        return 0
    if args.command == "run-worker":
        engine = sa.create_engine(settings.worker_database_url, pool_pre_ping=True)
        store = WorkspaceObjectStore(
            settings.object_store_root,
            chunk_bytes=settings.upload_chunk_bytes,
            max_file_bytes=settings.max_file_bytes,
        )
        worker_instance = DocumentWorker(
            SpinePostgresRepository(engine),
            store,
            worker_identity=args.identity,
            lease_seconds=settings.job_lease_seconds,
            qwen_vision_url=f"http://{settings.qwen_bind_host}:{settings.qwen_bind_port}/vision",
            qwen_semantic_url=f"http://{settings.qwen_bind_host}:{settings.qwen_bind_port}/generate",
            organization_id=settings.document_worker_organization_id,
            workspace_id=settings.document_worker_workspace_id,
        )
        try:
            worker_instance.run_forever()
        finally:
            engine.dispose()
        return 0
    if args.command == "run-assistant-worker":
        engine = sa.create_engine(settings.worker_database_url, pool_pre_ping=True)
        knowledge_engine = sa.create_engine(settings.database_url, pool_pre_ping=True)
        instance = AssistantWorker(
            AssistantRepository(engine),
            ProfessionalAssistantKnowledgeQuery(
                knowledge_engine,
                production_embedding_endpoint=settings.ntd_embedding_endpoint,
            ),
            identity=args.identity,
            qwen_url=f"http://{settings.qwen_bind_host}:{settings.qwen_bind_port}/generate",
        )
        try:
            instance.run_forever()
        finally:
            engine.dispose()
            knowledge_engine.dispose()
        return 0
    if args.command in {"run-ntd-worker", "enqueue-ntd-provisions"}:
        if settings.ntd_processing_database_url is None:
            raise ValueError("ASD_NTD_PROCESSING_DATABASE_URL is required")
        engine = sa.create_engine(settings.ntd_processing_database_url, pool_pre_ping=True)
        try:
            repository = LocalNtdProvisionRepository(engine)
            queued = repository.enqueue_bounded(
                eligible_at=datetime.now(UTC),
                limit=args.limit if args.command == "enqueue-ntd-provisions" else 2,
                profile_cap=args.profile_cap if args.command == "enqueue-ntd-provisions" else 20,
            )
            if args.command == "enqueue-ntd-provisions":
                print(
                    json.dumps(
                        {
                            "eligible": queued.eligible,
                            "inserted": queued.inserted,
                            "outstanding": queued.outstanding,
                            "capacity_remaining": queued.capacity_remaining,
                            "reason": queued.reason,
                        }
                    )
                )
                return 0
            LocalNtdProvisionWorker(
                engine,
                qwen_url=f"http://{settings.qwen_bind_host}:{settings.qwen_bind_port}/generate",
                identity=args.identity,
            ).run_forever()
        finally:
            engine.dispose()
        return 0
    if args.command == "reconcile-ntd-native-lineage":
        historical_url = os.environ.get("ASD_NTD_HISTORICAL_DATABASE_URL")
        if historical_url is None:
            raise ValueError("ASD_NTD_HISTORICAL_DATABASE_URL is required")
        if settings.ntd_processing_database_url is None:
            raise ValueError("ASD_NTD_PROCESSING_DATABASE_URL is required")
        historical_engine = sa.create_engine(historical_url, pool_pre_ping=True)
        target_engine = sa.create_engine(settings.ntd_processing_database_url, pool_pre_ping=True)
        try:
            result = reconcile_exact_native_lineage(
                historical_engine,
                target_engine,
                document_limit=args.document_limit,
            )
        finally:
            historical_engine.dispose()
            target_engine.dispose()
        print(json.dumps(asdict(result), sort_keys=True))
        return 0
    if args.command in {"status", "health"}:
        return _http_status(settings)
    if args.command == "stop":
        return _stop_launchd(args.service)
    if args.command == "logs":
        return _show_logs(settings, args.service, args.lines)
    if args.command == "render-launchd":
        _render_launchd(args.output, settings)
        return 0
    raise AssertionError("unreachable")


def _database_preflight(settings: SpineSettings) -> int:
    checks: dict[str, object] = {}
    for name, url in (
        ("application", settings.database_url),
        ("lifecycle", settings.lifecycle_database_url),
        ("worker", settings.worker_database_url),
    ):
        engine = sa.create_engine(url, pool_pre_ping=True)
        try:
            with engine.connect() as connection:
                checks[name] = {
                    "reachable": bool(connection.scalar(sa.text("SELECT true"))),
                    "migration_head": connection.scalar(
                        sa.text("SELECT version_num FROM alembic_version")
                    ),
                }
        finally:
            engine.dispose()
    checks["object_store"] = {
        "exists": settings.object_store_root.is_dir(),
        "is_symlink": settings.object_store_root.is_symlink(),
    }
    print(json.dumps(checks, default=str, sort_keys=True))
    application_ok = bool(checks["application"]["reachable"])  # type: ignore[index]
    lifecycle_ok = bool(checks["lifecycle"]["reachable"])  # type: ignore[index]
    worker_ok = bool(checks["worker"]["reachable"])  # type: ignore[index]
    object_store_ok = bool(checks["object_store"]["exists"])  # type: ignore[index]
    return 0 if application_ok and lifecycle_ok and worker_ok and object_store_ok else 1


def _migrate(settings: SpineSettings) -> int:
    repository = Path(__file__).resolve().parents[3]
    migration_database_url = os.environ.get("ASD_MIGRATION_DATABASE_URL", settings.database_url)
    if not migration_database_url.startswith(("postgresql+psycopg://", "postgresql://")):
        raise ValueError("ASD_MIGRATION_DATABASE_URL must be an explicit PostgreSQL URL")
    configuration = Config(str(repository / "alembic.ini"))
    configuration.set_main_option("sqlalchemy.url", migration_database_url)
    # ``migrations/env.py`` deliberately accepts the target connection only as
    # Alembic's explicit ``-x database_url=...`` argument.  The runtime command
    # must preserve that fail-closed contract instead of relying on the config
    # value, which the migration environment intentionally ignores.
    configuration.cmd_opts = argparse.Namespace(x=[f"database_url={migration_database_url}"])
    command.upgrade(configuration, "head")
    return 0


def _frontend_build() -> int:
    repository = Path(__file__).resolve().parents[3]
    frontend = repository / "frontend"
    subprocess.run(["npm", "ci"], cwd=frontend, check=True)
    subprocess.run(["npm", "run", "generate:api"], cwd=frontend, check=True)
    subprocess.run(["npm", "run", "build"], cwd=frontend, check=True)
    return 0


def _http_status(settings: SpineSettings) -> int:
    url = f"http://{settings.bind_host}:{settings.bind_port}/api/v1/health/ready"
    try:
        with urllib.request.urlopen(url, timeout=5) as response:
            payload = json.loads(response.read(65536))
    except (OSError, urllib.error.URLError, json.JSONDecodeError) as exc:
        print(json.dumps({"status": "unavailable", "exception_type": type(exc).__name__}))
        return 1
    print(json.dumps(payload, sort_keys=True))
    return 0 if payload.get("status") == "ready" else 1


def _log_root() -> Path:
    value = os.environ.get("ASD_LOG_ROOT")
    if not value:
        raise ValueError("ASD_LOG_ROOT is required for supervised logs")
    result = Path(value)
    if not result.is_absolute():
        raise ValueError("ASD_LOG_ROOT must be absolute")
    return result


def _stop_launchd(service: str) -> int:
    names = ("api", "worker", "assistant-worker", "qwen") if service == "all" else (service,)
    outcomes: dict[str, str] = {}
    for name in names:
        label = f"ru.asd-kontur.spine.{name}"
        completed = subprocess.run(
            ["launchctl", "kill", "TERM", f"gui/{os.getuid()}/{label}"],
            check=False,
            capture_output=True,
            text=True,
        )
        outcomes[name] = "signal_sent" if completed.returncode == 0 else "not_loaded"
    print(json.dumps({"services": outcomes}, sort_keys=True))
    return 0 if all(value == "signal_sent" for value in outcomes.values()) else 1


def _show_logs(settings: SpineSettings, service: str, lines: int) -> int:
    del settings
    if lines < 1 or lines > 1000:
        raise ValueError("log line count must be between 1 and 1000")
    names = ("api", "worker", "assistant-worker", "qwen") if service == "all" else (service,)
    root = _log_root()
    missing = False
    for name in names:
        path = root / f"{name}.log"
        print(json.dumps({"service": name, "path": str(path)}, sort_keys=True))
        if not path.is_file():
            print("log_unavailable")
            missing = True
            continue
        content = path.read_text(encoding="utf-8", errors="replace").splitlines()
        for line in content[-lines:]:
            print(line)
    return 1 if missing else 0


def _render_launchd(output: Path, settings: SpineSettings) -> None:
    if not output.is_absolute() or output.exists():
        raise ValueError("launchd output must be a new absolute path")
    output.mkdir(parents=True, mode=0o700)
    # Preserve the virtual-environment interpreter path. Resolving its symlink to
    # the uv-managed base interpreter drops the editable project environment when
    # launchd starts the service outside an interactive shell.
    executable = Path(sys.executable).absolute()
    log_root = _log_root()
    environment = {
        "ASD_DATABASE_URL": settings.database_url,
        "ASD_LIFECYCLE_DATABASE_URL": settings.lifecycle_database_url,
        "ASD_WORKER_DATABASE_URL": settings.worker_database_url,
        "ASD_DESTRUCTION_DATABASE_URL": settings.destruction_database_url,
        "ASD_OBJECT_STORE_ROOT": str(settings.object_store_root),
        "ASD_ARCHIVE_STORE_ROOT": str(settings.archive_store_root),
        "ASD_SESSION_PROFILE": settings.session_profile.value,
        "ASD_AUTH_AUDIT_PEPPER": settings.audit_pepper,
        "ASD_BIND_HOST": settings.bind_host,
        "ASD_BIND_PORT": str(settings.bind_port),
        "ASD_LOG_ROOT": str(log_root),
        "ASD_RELEASE_COMMIT": settings.release_commit,
        "ASD_RELEASE_PROFILE": settings.release_profile,
        "ASD_EXPECTED_MIGRATION_HEAD": settings.expected_migration_head,
    }
    optional_environment = {
        "ASD_FRONTEND_DIST": str(settings.frontend_dist) if settings.frontend_dist else None,
        "ASD_DEPLOYED_AT": settings.deployed_at,
        "ASD_FRONTEND_BUILD_DIGEST": settings.frontend_build_digest,
        "ASD_OPENAPI_DIGEST": settings.openapi_digest,
        "ASD_QWEN_RUNTIME_PYTHON": str(settings.qwen_runtime_python),
        "ASD_QWEN_MODEL_PATH": str(settings.qwen_model_path),
        "ASD_QWEN_BIND_HOST": settings.qwen_bind_host,
        "ASD_QWEN_BIND_PORT": str(settings.qwen_bind_port),
        "ASD_NTD_PROCESSING_DATABASE_URL": settings.ntd_processing_database_url,
        "ASD_NTD_PROCESSING_PGPASSFILE": (
            str(settings.ntd_processing_pgpassfile)
            if settings.ntd_processing_pgpassfile is not None
            else None
        ),
        "PGPASSFILE": (
            str(settings.ntd_processing_pgpassfile)
            if settings.ntd_processing_pgpassfile is not None
            else None
        ),
    }
    for variable_name, variable_value in optional_environment.items():
        if variable_value is not None:
            environment[variable_name] = variable_value
    environment_xml = "".join(
        f"<key>{escape(name)}</key><string>{escape(value)}</string>"
        for name, value in sorted(environment.items())
    )
    service_commands = [
        ("api", "serve-api"),
        ("worker", "run-worker"),
        ("assistant-worker", "run-assistant-worker"),
    ]
    if settings.ntd_processing_database_url is not None:
        service_commands.append(("ntd-worker", "run-ntd-worker"))
    for name, command_name in service_commands:
        log_path = log_root / f"{name}.log"
        content = (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" '
            '"http://www.apple.com/DTDs/PropertyList-1.0.dtd">\n'
            '<plist version="1.0"><dict>'
            f"<key>Label</key><string>ru.asd-kontur.spine.{name}</string>"
            "<key>ProgramArguments</key><array>"
            f"<string>{escape(str(executable))}</string><string>-m</string>"
            "<string>asd_kontur.application_spine.runtime</string>"
            f"<string>{command_name}</string></array>"
            f"<key>EnvironmentVariables</key><dict>{environment_xml}</dict>"
            f"<key>StandardOutPath</key><string>{escape(str(log_path))}</string>"
            f"<key>StandardErrorPath</key><string>{escape(str(log_path))}</string>"
            "<key>KeepAlive</key><true/><key>ThrottleInterval</key><integer>5</integer>"
            "<key>ProcessType</key><string>Background</string>"
            "</dict></plist>\n"
        )
        target = output / f"ru.asd-kontur.spine.{name}.plist"
        target.write_text(content, encoding="utf-8")
        target.chmod(0o600)
    qwen_log_path = log_root / "qwen.log"
    qwen_environment = (
        f"<key>PYTHONPATH</key><string>{escape(str(Path(__file__).resolve().parents[2]))}</string>"
    )
    qwen_content = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" '
        '"http://www.apple.com/DTDs/PropertyList-1.0.dtd">\n'
        '<plist version="1.0"><dict>'
        "<key>Label</key><string>ru.asd-kontur.spine.qwen</string>"
        "<key>ProgramArguments</key><array>"
        f"<string>{escape(str(settings.qwen_runtime_python))}</string><string>-m</string>"
        "<string>asd_kontur.assistant.qwen_server</string><string>--model</string>"
        f"<string>{escape(str(settings.qwen_model_path))}</string><string>--host</string>"
        f"<string>{escape(settings.qwen_bind_host)}</string><string>--port</string>"
        f"<string>{settings.qwen_bind_port}</string></array>"
        f"<key>EnvironmentVariables</key><dict>{qwen_environment}</dict>"
        f"<key>StandardOutPath</key><string>{escape(str(qwen_log_path))}</string>"
        f"<key>StandardErrorPath</key><string>{escape(str(qwen_log_path))}</string>"
        "<key>KeepAlive</key><true/><key>ThrottleInterval</key><integer>10</integer>"
        "<key>ProcessType</key><string>Interactive</string>"
        "</dict></plist>\n"
    )
    qwen_target = output / "ru.asd-kontur.spine.qwen.plist"
    qwen_target.write_text(qwen_content, encoding="utf-8")
    qwen_target.chmod(0o600)
    rotation_names = ["api", "worker", "assistant-worker"]
    if settings.ntd_processing_database_url is not None:
        rotation_names.append("ntd-worker")
    rotation_names.append("qwen")
    rotation = "\n".join(
        f"{log_root / f'{name}.log'}  640  10  10240  *  J" for name in rotation_names
    )
    (output / "asd-kontur-spine.newsyslog.conf").write_text(rotation + "\n", encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
