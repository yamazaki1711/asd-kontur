"""Disposable PostgreSQL construction and deterministic inventory functions."""

from __future__ import annotations

import os
import subprocess
from argparse import Namespace
from collections.abc import Iterable
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine
from sqlalchemy.engine import URL

from .models import IntegrityFailure, canonical_digest

DISPOSABLE_PREFIX = "asd_integrity_"


def _assert_disposable_name(database_name: str) -> None:
    if (
        not database_name.startswith(DISPOSABLE_PREFIX)
        or not database_name.replace("_", "").isalnum()
    ):
        raise IntegrityFailure(
            "UNSAFE_DATABASE_TARGET",
            f"database must use the {DISPOSABLE_PREFIX!r} prefix",
        )


def create_database(cluster_engine: Engine, database_name: str) -> None:
    _assert_disposable_name(database_name)
    with cluster_engine.connect() as connection:
        connection.exec_driver_sql(f'CREATE DATABASE "{database_name}"')


def drop_database(cluster_engine: Engine, database_name: str) -> None:
    _assert_disposable_name(database_name)
    with cluster_engine.connect() as connection:
        connection.exec_driver_sql(
            "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
            "WHERE datname = %s AND pid <> pg_backend_pid()",
            (database_name,),
        )
        connection.exec_driver_sql(f'DROP DATABASE IF EXISTS "{database_name}"')


def migrate(repository_root: Path, database_url: URL, revision: str) -> None:
    configuration = Config(str(repository_root / "alembic.ini"))
    configuration.cmd_opts = Namespace(
        x=[f"database_url={database_url.render_as_string(hide_password=False)}"]
    )
    if revision == "head":
        command.upgrade(configuration, revision)
    else:
        prior = os.environ.get("ASD_ALLOW_DESTRUCTIVE_DOWNGRADE")
        os.environ["ASD_ALLOW_DESTRUCTIVE_DOWNGRADE"] = "1"
        try:
            command.downgrade(configuration, revision)
        finally:
            if prior is None:
                os.environ.pop("ASD_ALLOW_DESTRUCTIVE_DOWNGRADE", None)
            else:
                os.environ["ASD_ALLOW_DESTRUCTIVE_DOWNGRADE"] = prior


def restore_custom_dump(*, database_url: URL, dump_path: Path) -> None:
    if not dump_path.is_file():
        raise IntegrityFailure("BACKUP_OBJECT_UNAVAILABLE", "qualification backup is unavailable")
    command_line = [
        "pg_restore",
        "--host",
        database_url.host or "localhost",
        "--port",
        str(database_url.port or 5432),
        "--username",
        database_url.username or "",
        "--dbname",
        database_url.database or "",
        "--no-owner",
        "--no-privileges",
        "--exit-on-error",
        str(dump_path),
    ]
    environment = dict(os.environ)
    if database_url.password:
        environment["PGPASSWORD"] = database_url.password
    completed = subprocess.run(
        command_line,
        capture_output=True,
        check=False,
        text=True,
        timeout=300,
        env=environment,
    )
    if completed.returncode:
        raise IntegrityFailure(
            "BACKUP_RESTORE_FAILED",
            "pg_restore did not complete",
            evidence={"returncode": completed.returncode},
        )


def _plain(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, bytes):
        return value.hex()
    if isinstance(value, dict):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    return value


def schema_inventory(engine: Engine) -> dict[str, Any]:
    queries = {
        "columns": """
            SELECT table_schema,table_name,column_name,data_type,
                   udt_schema,udt_name,is_nullable,column_default,identity_generation
            FROM information_schema.columns
            WHERE table_schema IN ('public','organization','workspace','platform',
                                   'projection','audit','messaging')
            ORDER BY 1,2,3
        """,
        "constraints": """
            SELECT n.nspname,c.relname,k.conname,k.contype,pg_get_constraintdef(k.oid,true)
            FROM pg_constraint k JOIN pg_class c ON c.oid=k.conrelid
            JOIN pg_namespace n ON n.oid=c.relnamespace
            WHERE n.nspname IN ('public','organization','workspace','platform',
                                'projection','audit','messaging')
            ORDER BY 1,2,3
        """,
        "indexes": """
            SELECT schemaname,tablename,indexname,indexdef
            FROM pg_indexes
            WHERE schemaname IN ('public','organization','workspace','platform',
                                 'projection','audit','messaging')
            ORDER BY 1,2,3
        """,
        "functions": """
            SELECT n.nspname,p.proname,pg_get_function_identity_arguments(p.oid),
                   pg_get_functiondef(p.oid)
            FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
            WHERE n.nspname IN
                  ('organization','workspace','platform','projection','audit','messaging')
            ORDER BY 1,2,3
        """,
        "triggers": """
            SELECT n.nspname,c.relname,t.tgname,pg_get_triggerdef(t.oid,true)
            FROM pg_trigger t JOIN pg_class c ON c.oid=t.tgrelid
            JOIN pg_namespace n ON n.oid=c.relnamespace
            WHERE NOT t.tgisinternal AND n.nspname IN
                  ('organization','workspace','platform','projection','audit','messaging')
            ORDER BY 1,2,3
        """,
        "policies": """
            SELECT schemaname,tablename,policyname,permissive,roles,cmd,qual,with_check
            FROM pg_policies
            WHERE schemaname IN
                  ('organization','workspace','platform','projection','audit','messaging')
            ORDER BY 1,2,3
        """,
        "rls": """
            SELECT n.nspname,c.relname,c.relrowsecurity,c.relforcerowsecurity
            FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
            WHERE c.relkind='r' AND n.nspname IN
                  ('organization','workspace','platform','projection','audit','messaging')
            ORDER BY 1,2
        """,
    }
    inventory: dict[str, Any] = {}
    with engine.connect() as connection:
        for key, query in queries.items():
            inventory[key] = [_plain(tuple(row)) for row in connection.execute(sa.text(query))]
    return inventory


def schema_fingerprint(engine: Engine) -> str:
    return canonical_digest(schema_inventory(engine))


PERMANENT_TABLES = (
    "source_artifacts",
    "source_versions",
    "practice_guides",
    "practice_guide_editions",
    "practice_guide_edition_activation_decisions",
    "practice_guidance_units",
    "practice_guidance_gaps",
    "practice_guidance_conflicts",
    "practice_intelligence_units",
    "practice_playbooks",
    "practice_context_assembly_policies",
    "practice_memory_releases",
    "practice_guide_normative_references",
    "ntd_acquisition_receipts",
    "ntd_gaps",
    "normative_documents",
    "normative_editions",
    "normative_provision_versions",
    "rule_versions",
    "rule_version_states",
    "rule_set_versions",
)


def platform_memory_inventory(engine: Engine) -> dict[str, Any]:
    inspector = sa.inspect(engine)
    existing = set(inspector.get_table_names(schema="platform"))
    inventory: dict[str, Any] = {}
    with engine.connect() as connection:
        for table in PERMANENT_TABLES:
            if table not in existing:
                inventory[table] = {"present": False, "rows": []}
                continue
            columns = [item["name"] for item in inspector.get_columns(table, schema="platform")]
            selected = [column for column in columns if not column.endswith("_at")]
            quoted = ",".join(f'"{column}"' for column in selected)
            rows = [
                _plain(dict(row._mapping))
                for row in connection.execute(sa.text(f'SELECT {quoted} FROM platform."{table}"'))
            ]
            rows.sort(key=lambda item: canonical_digest(item))
            inventory[table] = {"present": True, "rows": rows}
    return inventory


def platform_memory_fingerprint(engine: Engine) -> str:
    return canonical_digest(platform_memory_inventory(engine))


def platform_memory_counts(engine: Engine) -> dict[str, int]:
    inspector = sa.inspect(engine)
    existing = set(inspector.get_table_names(schema="platform"))
    with engine.connect() as connection:
        return {
            table: int(connection.scalar(sa.text(f'SELECT count(*) FROM platform."{table}"')))
            for table in PERMANENT_TABLES
            if table in existing
        }


def assert_no_workspace_ownership(engine: Engine) -> None:
    inspector = sa.inspect(engine)
    violations: list[str] = []
    for table in PERMANENT_TABLES:
        if table not in set(inspector.get_table_names(schema="platform")):
            continue
        columns = {item["name"] for item in inspector.get_columns(table, schema="platform")}
        if "workspace_id" in columns or "organization_id" in columns:
            violations.append(table)
    if violations:
        raise IntegrityFailure(
            "PLATFORM_MEMORY_WORKSPACE_OWNED",
            "permanent platform memory contains workspace ownership columns",
            evidence={"tables": violations},
        )


def assert_expected_counts(actual: dict[str, int], expected: dict[str, int]) -> None:
    differences = {
        key: {"expected": value, "actual": actual.get(key)}
        for key, value in expected.items()
        if actual.get(key) != value
    }
    if differences:
        raise IntegrityFailure(
            "PLATFORM_MEMORY_COUNT_MISMATCH",
            "restored qualification snapshot counts differ",
            evidence={"differences": differences},
        )


def duplicate_identity_inventory(engine: Engine) -> dict[str, list[tuple[Any, ...]]]:
    checks = {
        "migration_revisions": (
            "SELECT version_num,count(*) FROM alembic_version GROUP BY 1 HAVING count(*)>1"
        ),
        "source_versions": (
            "SELECT source_version_id,count(*) FROM platform.source_versions "
            "GROUP BY 1 HAVING count(*)>1"
        ),
        "practice_editions": (
            "SELECT practice_guide_edition_id,count(*) FROM platform.practice_guide_editions "
            "GROUP BY 1 HAVING count(*)>1"
        ),
    }
    output: dict[str, list[tuple[Any, ...]]] = {}
    with engine.connect() as connection:
        for key, query in checks.items():
            output[key] = [tuple(row) for row in connection.execute(sa.text(query))]
    return output


def assert_no_partial_state(engine: Engine, table_names: Iterable[str]) -> None:
    inspector = sa.inspect(engine)
    workspace_tables = set(inspector.get_table_names(schema="workspace"))
    missing = sorted(set(table_names) - workspace_tables)
    if missing:
        raise IntegrityFailure(
            "PARTIAL_SCHEMA_STATE",
            "expected head tables are missing",
            evidence={"missing": missing},
        )
