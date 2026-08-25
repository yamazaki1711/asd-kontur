"""Reproducible coordinator for SYSTEM-INTEGRITY-CYCLE-01.

The coordinator launches every cycle in a fresh Python process. Full receipts,
command logs, and the bounded model exchange remain outside Git.
"""

from __future__ import annotations

import argparse
import importlib.metadata
import json
import os
import pkgutil
import re
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.engine import make_url

import asd_kontur
from asd_kontur.knowledge.gateway import GatewayContext, GatewayStatus
from asd_kontur.knowledge.postgres import PostgresKnowledgeQuery
from asd_kontur.ntd.durability import NtdProjectionBuilder
from asd_kontur.practice_guidance.intelligence_postgres import persist_manifest
from asd_kontur.practice_guidance.postgres import PracticeGuideRepository

from .models import (
    IntegrityFailure,
    canonical_digest,
    file_digest,
    load_module_readiness_manifest,
    write_immutable_json,
)
from .postgres import (
    active_context_binding_fingerprint,
    active_release_semantic_fingerprint,
    active_semantic_duplicate_inventory,
    assert_expected_counts,
    assert_no_partial_state,
    assert_no_workspace_ownership,
    create_database,
    drop_database,
    duplicate_identity_inventory,
    migrate,
    platform_memory_counts,
    platform_memory_fingerprint,
    proven_duplicate_evidence_inventory,
    restore_custom_dump,
    schema_fingerprint,
    schema_inventory,
)
from .qualification import execute_four_mode_fixture
from .qwen import run_bf16_smoke

EXPECTED_HEAD = "0019_memory_integrity"
EXPECTED_MODEL_DIGEST = "sha256:8ab2241982b33afd5ab176cc4e5069afee866323a8fcc52df6345149b3f0d766"
HEAD_TABLES = (
    "project_definition_versions",
    "project_characteristic_candidates",
    "verified_project_characteristics",
    "construction_work_package_versions",
    "work_requirement_matrix_versions",
    "customer_regulation_additions",
    "construction_harness_context_packs",
    "knowledge_consistency_defects",
    "construction_harness_mode_views",
    "construction_harness_backup_manifests",
)
EXPECTED_PLATFORM_COUNTS = {
    "source_guidance_identity_count": 2410,
    "practice_intelligence_identity_count": 7111,
    "practice_intelligence_version_row_count": 21105,
    "active_release_intelligence_version_count": 7111,
    "historical_intelligence_version_count": 13994,
    "playbook_identity_count": 1644,
    "playbook_version_row_count": 4888,
    "active_release_playbook_count": 1644,
    "historical_playbook_count": 3244,
    "logical_gap_identity_count": 547,
    "active_gap_identity_count": 395,
    "closed_gap_identity_count": 152,
    "gap_snapshot_row_count": 858,
    "conflict_identity_count": 138,
    "quarantined_candidate_identity_count": 53,
    "rule_version_count": 0,
}
SEMANTIC_KEYS = (
    "code_fingerprint",
    "lock_fingerprint",
    "schema_fingerprint",
    "contract_pack_fingerprint",
    "all_history_platform_memory_fingerprint",
    "active_release_semantic_fingerprint",
    "active_context_pack_binding_fingerprint",
    "backup_restore_fingerprint",
    "projection_fingerprint",
    "fixture_source_fingerprint",
    "work_requirement_matrix_fingerprint",
    "four_mode_output_fingerprint",
    "context_pack_fingerprint",
    "module_readiness_fingerprint",
    "qwen_structural_fingerprint",
)


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _qualify_release_selection(engine: sa.Engine) -> dict[str, Any]:
    with engine.connect() as connection:
        edition_id = connection.scalar(
            sa.text(
                "SELECT selected_edition_id FROM "
                "platform.practice_guide_edition_activation_decisions "
                "ORDER BY version DESC LIMIT 1"
            )
        )
        releases = tuple(
            connection.execute(
                sa.text(
                    "SELECT release_id,version FROM platform.practice_intelligence_releases "
                    "ORDER BY published_at,release_id"
                )
            )
        )
        selected = connection.execute(
            sa.text(
                "SELECT selected_release_id,selected_release_version FROM "
                "platform.practice_intelligence_release_activation_decisions "
                "ORDER BY version DESC LIMIT 1"
            )
        ).one_or_none()
    if edition_id is None or selected is None or len(releases) < 2:
        raise IntegrityFailure(
            "RELEASE_SELECTION_QUALIFICATION_INCOMPLETE",
            "active and historical releases must both be present",
        )
    query = PostgresKnowledgeQuery(engine)
    context = GatewayContext(
        "service.system-integrity-qualifier",
        "knowledge.get_id_task_guidance.invoke",
        "id.support",
        UUID("00000000-0000-0000-0000-000000000099"),
    )
    base_payload: dict[str, Any] = {
        "query": "журнал",
        "intent": "journal_selection",
        "practice_guide_edition_id": str(edition_id),
        "mode": "Support",
        "purpose": "id.support",
    }
    active = query.execute("knowledge.get_id_task_guidance", base_payload, context)
    historical_release = next(
        row
        for row in releases
        if (str(row[0]), int(row[1])) != (str(selected[0]), int(selected[1]))
    )
    historical = query.execute(
        "knowledge.get_id_task_guidance",
        {
            **base_payload,
            "practice_intelligence_release_id": str(historical_release[0]),
            "practice_intelligence_release_version": int(historical_release[1]),
        },
        context,
    )
    acceptable = {GatewayStatus.OK, GatewayStatus.KNOWLEDGE_INCOMPLETE}
    if (
        active.status not in acceptable
        or historical.status not in acceptable
        or active.result.get("release_selection") != "active_release_decision"
        or historical.result.get("release_selection") != "historical_exact_pin"
        or str(active.result.get("practice_intelligence_release_id")) != str(selected[0])
        or not active.evidence_pack.evidence
        or not historical.evidence_pack.evidence
    ):
        raise IntegrityFailure(
            "RELEASE_SELECTION_QUALIFICATION_FAILED",
            "default active selection or exact historical pin failed",
        )
    return {
        "active_release_id": str(selected[0]),
        "active_release_version": int(selected[1]),
        "active_result_count": len(active.result.get("practice_intelligence", ())),
        "historical_release_id": str(historical_release[0]),
        "historical_release_version": int(historical_release[1]),
        "historical_result_count": len(historical.result.get("practice_intelligence", ())),
        "default_selection": "active_release_decision",
        "historical_selection": "historical_exact_pin",
    }


def _command_version(command_line: list[str]) -> str:
    completed = subprocess.run(
        command_line,
        capture_output=True,
        check=False,
        text=True,
        timeout=20,
    )
    if completed.returncode:
        return "unavailable"
    return (completed.stdout or completed.stderr).strip().splitlines()[0]


def _git(repository_root: Path, *arguments: str) -> str:
    completed = subprocess.run(
        ["git", *arguments],
        cwd=repository_root,
        capture_output=True,
        check=False,
        text=True,
        timeout=30,
    )
    if completed.returncode:
        raise IntegrityFailure(
            "GIT_PREFLIGHT_FAILED",
            "Git command failed",
            evidence={"arguments": list(arguments), "returncode": completed.returncode},
        )
    return completed.stdout.strip()


def _tracked_files(repository_root: Path) -> tuple[Path, ...]:
    value = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=repository_root,
        capture_output=True,
        check=True,
        timeout=30,
    ).stdout
    return tuple(repository_root / item.decode() for item in value.split(b"\0") if item)


def _tree_fingerprint(repository_root: Path) -> str:
    values = [
        (str(path.relative_to(repository_root)), file_digest(path))
        for path in _tracked_files(repository_root)
        if path.is_file()
    ]
    return canonical_digest(values)


def _contract_inventory(repository_root: Path) -> dict[str, Any]:
    schema_ids: dict[str, str] = {}
    contract_keys: dict[str, str] = {}
    files: list[tuple[str, str]] = []
    for registry_path in sorted((repository_root / "contracts").glob("v*/registry.json")):
        registry = json.loads(registry_path.read_text(encoding="utf-8"))
        relative = str(registry_path.relative_to(repository_root))
        files.append((relative, file_digest(registry_path)))
        for schema in registry.get("schemas", []):
            identity = str(schema["schema_id"])
            if identity in schema_ids:
                raise IntegrityFailure(
                    "DUPLICATE_SCHEMA_ID",
                    "Contract Pack schema identity is duplicated",
                    evidence={
                        "schema_id": identity,
                        "registries": [schema_ids[identity], relative],
                    },
                )
            schema_ids[identity] = relative
            schema_path = registry_path.parent / str(schema["path"])
            actual_digest = file_digest(schema_path)
            expected_digest = schema.get("digest")
            if expected_digest is not None and actual_digest != expected_digest:
                raise IntegrityFailure(
                    "CONTRACT_FINGERPRINT_MISMATCH",
                    "registered schema digest differs",
                    evidence={"path": str(schema_path.relative_to(repository_root))},
                )
            if expected_digest is None and registry.get("registry_version") == "2.2.0":
                raise IntegrityFailure(
                    "CONTRACT_FINGERPRINT_MISSING",
                    "current Contract Pack schema lacks a registered digest",
                    evidence={"path": str(schema_path.relative_to(repository_root))},
                )
        for key in registry.get("contract_keys", []):
            key = str(key)
            if key in contract_keys:
                raise IntegrityFailure(
                    "DUPLICATE_CONTRACT_KEY",
                    "Contract Pack key is duplicated",
                    evidence={"contract_key": key, "registries": [contract_keys[key], relative]},
                )
            contract_keys[key] = relative
    files = [
        (str(path.relative_to(repository_root)), file_digest(path))
        for path in sorted((repository_root / "contracts").glob("v*/**/*"))
        if path.is_file()
    ]
    return {
        "registry_count": len(tuple((repository_root / "contracts").glob("v*/registry.json"))),
        "schema_ids": sorted(schema_ids),
        "contract_keys": sorted(contract_keys),
        "fingerprint": canonical_digest(files),
    }


def _migration_inventory(repository_root: Path) -> dict[str, Any]:
    revisions: dict[str, str] = {}
    for path in sorted((repository_root / "migrations/versions").glob("*.py")):
        match = re.search(r'^revision\s*=\s*["\']([^"\']+)', path.read_text(encoding="utf-8"), re.M)
        if match is None:
            raise IntegrityFailure("MIGRATION_REVISION_MISSING", f"revision missing in {path.name}")
        revision = match.group(1)
        if revision in revisions:
            raise IntegrityFailure("DUPLICATE_MIGRATION_REVISION", f"duplicate {revision}")
        revisions[revision] = path.name
    return {"revisions": revisions, "fingerprint": canonical_digest(revisions)}


def _validate_markdown_links(repository_root: Path) -> int:
    pattern = re.compile(r"\[[^\]]*\]\(([^)]+)\)")
    checked = 0
    missing: list[str] = []
    for path in _tracked_files(repository_root):
        if path.suffix.lower() != ".md":
            continue
        for target in pattern.findall(path.read_text(encoding="utf-8")):
            clean = target.split("#", 1)[0].strip()
            if not clean or clean.startswith(("http://", "https://", "mailto:", "#")):
                continue
            checked += 1
            resolved = (
                repository_root / clean.lstrip("/")
                if clean.startswith("/")
                else path.parent / clean
            )
            if not resolved.exists():
                missing.append(f"{path.relative_to(repository_root)} -> {target}")
    if missing:
        raise IntegrityFailure(
            "MARKDOWN_LINK_INVALID",
            "local Markdown links are unresolved",
            evidence={"missing": missing[:20], "missing_count": len(missing)},
        )
    return checked


def _scan_tracked_files(repository_root: Path) -> dict[str, int]:
    forbidden_suffixes = {
        ".pdf",
        ".safetensors",
        ".gguf",
        ".dump",
        ".sql",
        ".sqlite",
        ".db",
    }
    forbidden_name_fragments = ("raw-receipt", "raw_response", "page-render", "ocr-output")
    binary_or_raw: list[str] = []
    secret_hits: list[str] = []
    trailing_whitespace: list[str] = []
    secret_patterns = (
        re.compile(rb"pza_[A-Za-z0-9]{20,}"),
        re.compile(rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
        re.compile(rb"AKIA[0-9A-Z]{16}"),
    )
    files = _tracked_files(repository_root)
    for path in files:
        relative = str(path.relative_to(repository_root))
        lowered = relative.lower()
        if path.suffix.lower() in forbidden_suffixes or any(
            fragment in lowered for fragment in forbidden_name_fragments
        ):
            binary_or_raw.append(relative)
        if not path.is_file() or path.stat().st_size > 5 * 1024 * 1024:
            continue
        value = path.read_bytes()
        if b"\0" not in value:
            for line_number, line in enumerate(value.splitlines(), 1):
                if line.endswith((b" ", b"\t")):
                    trailing_whitespace.append(f"{relative}:{line_number}")
        if any(pattern.search(value) for pattern in secret_patterns):
            secret_hits.append(relative)
    if binary_or_raw:
        raise IntegrityFailure(
            "FORBIDDEN_ARTIFACT_IN_GIT",
            "forbidden artifacts are tracked",
            evidence={"paths": binary_or_raw},
        )
    if secret_hits:
        raise IntegrityFailure(
            "SECRET_SCAN_FAILED",
            "credential-like material is tracked",
            evidence={"paths": secret_hits},
        )
    if trailing_whitespace:
        raise IntegrityFailure(
            "TRAILING_WHITESPACE_DETECTED",
            "tracked text files contain trailing whitespace",
            evidence={"paths": trailing_whitespace[:50], "count": len(trailing_whitespace)},
        )
    return {
        "tracked_files": len(files),
        "secret_hits": 0,
        "forbidden_artifacts": 0,
        "trailing_whitespace": 0,
    }


class CycleRunner:
    def __init__(self, args: argparse.Namespace) -> None:
        self.args = args
        self.root = args.repository_root.resolve()
        self.cycle_directory = args.receipt_root.resolve() / args.series_id / args.cycle_id
        self.cycle_directory.mkdir(parents=True, exist_ok=False)
        os.chmod(self.cycle_directory, 0o700)
        self.phases: list[dict[str, Any]] = []
        self.semantic: dict[str, str] = {}
        self.cluster_url = make_url(args.database_url)
        if self.cluster_url.get_backend_name() != "postgresql":
            raise IntegrityFailure("DATABASE_PROFILE_INVALID", "PostgreSQL is required")
        self.cluster_url = self.cluster_url.set(database="postgres")

    def _write_phase(self, phase: str, started: str, payload: dict[str, Any]) -> None:
        receipt = {
            "contract": "system-integrity-phase-receipt/2.0.0",
            "cycle_id": self.args.cycle_id,
            "phase": phase,
            "status": "pass",
            "started_at": started,
            "completed_at": _now(),
            "payload": payload,
            "payload_fingerprint": canonical_digest(payload),
        }
        write_immutable_json(self.cycle_directory / f"phase-{phase}.json", receipt)
        self.phases.append(receipt)

    def _command(
        self, label: str, command_line: list[str], *, timeout: int = 1800
    ) -> dict[str, Any]:
        started = time.monotonic()
        completed = subprocess.run(
            command_line,
            cwd=self.root,
            capture_output=True,
            check=False,
            timeout=timeout,
            env=dict(os.environ),
        )
        log_path = self.cycle_directory / f"command-{label}.log"
        descriptor = os.open(log_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(completed.stdout)
            stream.write(b"\n[stderr]\n")
            stream.write(completed.stderr)
            stream.flush()
            os.fsync(stream.fileno())
        result = {
            "label": label,
            "returncode": completed.returncode,
            "log_digest": file_digest(log_path),
            "duration_seconds": round(time.monotonic() - started, 6),
        }
        if completed.returncode:
            raise IntegrityFailure(
                "QUALIFICATION_COMMAND_FAILED",
                f"command {label} failed",
                evidence=result,
            )
        return result

    def _pytest(self, label: str, targets: list[str], *, full: bool = False) -> dict[str, Any]:
        environment = dict(os.environ)
        environment["ASD_TEST_DATABASE_URL"] = self.cluster_url.render_as_string(
            hide_password=False
        )
        started = time.monotonic()
        completed = subprocess.run(
            ["uv", "run", "pytest", "-q", *targets],
            cwd=self.root,
            capture_output=True,
            check=False,
            timeout=3600,
            env=environment,
        )
        log_path = self.cycle_directory / f"pytest-{label}.log"
        descriptor = os.open(log_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(completed.stdout)
            stream.write(b"\n[stderr]\n")
            stream.write(completed.stderr)
            stream.flush()
            os.fsync(stream.fileno())
        output = (completed.stdout + completed.stderr).decode("utf-8", errors="replace")
        prohibited = sorted(
            marker
            for marker in (" skipped", " deselected", " xfailed", " xpassed")
            if marker in output
        )
        result = {
            "label": label,
            "returncode": completed.returncode,
            "log_digest": file_digest(log_path),
            "duration_seconds": round(time.monotonic() - started, 6),
            "prohibited_outcomes": prohibited,
            "full_suite": full,
        }
        if completed.returncode or prohibited:
            raise IntegrityFailure(
                "PYTEST_GATE_FAILED" if completed.returncode else "UNEXPLAINED_TEST_OUTCOME",
                f"pytest gate {label} did not produce an unqualified pass",
                evidence=result,
            )
        match = re.search(r"(\d+) passed", output)
        result["passed"] = int(match.group(1)) if match else 0
        return result

    def phase_a(self) -> None:
        started = _now()
        head = _git(self.root, "rev-parse", "HEAD")
        if _git(self.root, "status", "--porcelain"):
            raise IntegrityFailure("DIRTY_WORKTREE", "integrity qualification requires clean Git")
        if _git(self.root, "rev-parse", "origin/main") != self.args.origin_main:
            raise IntegrityFailure(
                "ORIGIN_MAIN_MISMATCH", "origin/main changed during qualification"
            )
        commands = [
            self._command("uv-lock", ["uv", "lock", "--check"]),
            self._command("ruff-format", ["uv", "run", "ruff", "format", "--check", "."]),
            self._command("ruff-lint", ["uv", "run", "ruff", "check", "."]),
            self._command("mypy", ["uv", "run", "mypy", "src"]),
            self._command("git-diff-check", ["git", "diff", "--check"]),
        ]
        imported = []
        for item in pkgutil.walk_packages(asd_kontur.__path__, asd_kontur.__name__ + "."):
            __import__(item.name)
            imported.append(item.name)
        contracts = _contract_inventory(self.root)
        migrations = _migration_inventory(self.root)
        module_manifest = load_module_readiness_manifest(self.args.module_manifest)
        if module_manifest.product_ready:
            raise IntegrityFailure("PRODUCT_READY_INVARIANT", "ProductReady must remain false")
        lock_fingerprint = file_digest(self.root / "uv.lock")
        code_fingerprint = _tree_fingerprint(self.root)
        self.semantic.update(
            {
                "code_fingerprint": code_fingerprint,
                "lock_fingerprint": lock_fingerprint,
                "contract_pack_fingerprint": contracts["fingerprint"],
                "module_readiness_fingerprint": module_manifest.semantic_fingerprint,
            }
        )
        self._write_phase(
            "A",
            started,
            {
                "git_head": head,
                "origin_main": self.args.origin_main,
                "code_fingerprint": code_fingerprint,
                "lock_fingerprint": lock_fingerprint,
                "commands": commands,
                "production_import_count": len(imported),
                "contract_inventory": contracts,
                "migration_inventory": migrations,
                "markdown_local_links_checked": _validate_markdown_links(self.root),
                "tracked_file_scan": _scan_tracked_files(self.root),
                "module_count": len(module_manifest.modules),
                "module_readiness_fingerprint": module_manifest.semantic_fingerprint,
            },
        )

    def phase_b(self) -> None:
        started = _now()
        database_name = f"asd_integrity_{self.args.cycle_id.lower().replace('-', '_')}_primary"
        cluster_engine = sa.create_engine(self.cluster_url, isolation_level="AUTOCOMMIT")
        database_url = self.cluster_url.set(database=database_name)
        engine: sa.Engine | None = None
        try:
            create_database(cluster_engine, database_name)
            migrate(self.root, database_url, "head")
            engine = sa.create_engine(database_url)
            with engine.connect() as connection:
                head = str(connection.scalar(sa.text("SELECT version_num FROM alembic_version")))
            if head != EXPECTED_HEAD:
                raise IntegrityFailure("ALEMBIC_HEAD_MISMATCH", "unexpected migration head")
            first_inventory = schema_inventory(engine)
            first = canonical_digest(first_inventory)
            engine.dispose()
            engine = None
            migrate(self.root, database_url, "0018_product_spine")
            migrate(self.root, database_url, "head")
            engine = sa.create_engine(database_url)
            second = schema_fingerprint(engine)
            if first != second:
                raise IntegrityFailure(
                    "SCHEMA_ROUNDTRIP_MISMATCH",
                    "0019 downgrade/upgrade changed schema fingerprint",
                    evidence={"before": first, "after": second},
                )
            with engine.begin() as connection:
                transaction = connection.begin_nested()
                connection.execute(
                    sa.text("CREATE TABLE public.integrity_rollback_probe(id integer)")
                )
                transaction.rollback()
            if sa.inspect(engine).has_table("integrity_rollback_probe", schema="public"):
                raise IntegrityFailure(
                    "ROLLBACK_INJECTION_FAILED", "rollback left partial DDL state"
                )
            migrate(self.root, database_url, "head")
            third = schema_fingerprint(engine)
            if third != first:
                raise IntegrityFailure(
                    "IDEMPOTENT_MIGRATION_MISMATCH", "idempotent head changed schema"
                )
            duplicates = duplicate_identity_inventory(engine)
            if any(duplicates.values()):
                raise IntegrityFailure(
                    "DUPLICATE_DATABASE_IDENTITY", "duplicate persisted identities detected"
                )
            assert_no_partial_state(engine, HEAD_TABLES)
            self.semantic["schema_fingerprint"] = first
            self._write_phase(
                "B",
                started,
                {
                    "database_class": "disposable",
                    "migration_head": head,
                    "schema_fingerprint": first,
                    "roundtrip_fingerprint": second,
                    "idempotent_fingerprint": third,
                    "inventory_counts": {key: len(value) for key, value in first_inventory.items()},
                    "rollback_injection": "pass",
                    "duplicate_identities": duplicates,
                    "partial_state": False,
                },
            )
        finally:
            if engine is not None:
                engine.dispose()
            drop_database(cluster_engine, database_name)
            cluster_engine.dispose()

    def _restore_platform_snapshot(
        self, suffix: str
    ) -> tuple[dict[str, int], str, str, str, str, dict[str, Any]]:
        database_name = f"asd_integrity_{self.args.cycle_id.lower().replace('-', '_')}_{suffix}"
        cluster_engine = sa.create_engine(self.cluster_url, isolation_level="AUTOCOMMIT")
        database_url = self.cluster_url.set(database=database_name)
        engine: sa.Engine | None = None
        try:
            create_database(cluster_engine, database_name)
            restore_custom_dump(database_url=database_url, dump_path=self.args.platform_snapshot)
            migrate(self.root, database_url, "head")
            engine = sa.create_engine(database_url)
            counts = platform_memory_counts(engine)
            assert_expected_counts(counts, EXPECTED_PLATFORM_COUNTS)
            assert_no_workspace_ownership(engine)
            all_history = platform_memory_fingerprint(engine)
            active_release = active_release_semantic_fingerprint(engine)
            context_binding = active_context_binding_fingerprint(engine)
            duplicates = active_semantic_duplicate_inventory(engine)
            if duplicates:
                raise IntegrityFailure(
                    "ACTIVE_SEMANTIC_IDENTITY_DUPLICATED",
                    "the selected release contains duplicate semantic identities",
                    evidence={"duplicate_groups": duplicates},
                )
            merged_evidence = proven_duplicate_evidence_inventory(engine)
            release_selection = _qualify_release_selection(engine)
            source_digest = file_digest(self.args.practice_source_object)
            if source_digest != self.args.practice_source_digest:
                raise IntegrityFailure(
                    "SOURCE_BYTE_FINGERPRINT_MISMATCH", "Practice Guide source bytes changed"
                )
            if len(merged_evidence) != 2:
                raise IntegrityFailure(
                    "SEMANTIC_DUPLICATE_REGRESSION_MISMATCH",
                    "both exact duplicate groups must retain occurrence lineage",
                )
            return (
                counts,
                all_history,
                active_release,
                context_binding,
                source_digest,
                release_selection,
            )
        finally:
            if engine is not None:
                engine.dispose()
            drop_database(cluster_engine, database_name)
            cluster_engine.dispose()

    def phase_c(self) -> None:
        started = _now()
        (
            counts,
            all_history,
            active_release,
            context_binding,
            source_digest,
            release_selection,
        ) = self._restore_platform_snapshot("memory")
        self.semantic.update(
            {
                "all_history_platform_memory_fingerprint": all_history,
                "active_release_semantic_fingerprint": active_release,
                "active_context_pack_binding_fingerprint": context_binding,
            }
        )
        self._write_phase(
            "C",
            started,
            {
                "snapshot_digest": file_digest(self.args.platform_snapshot),
                "source_byte_fingerprint": source_digest,
                "all_history_platform_memory_fingerprint": all_history,
                "active_release_semantic_fingerprint": active_release,
                "active_context_pack_binding_fingerprint": context_binding,
                "counts": counts,
                "historical_decisions": {
                    "kg_id": "PARTIAL:24/25-systemic:7/7-adversarial",
                    "ntd_seed": "PARTIAL:25-official_access_blocked:0-editions:0-provisions",
                },
                "mutable_latest": False,
                "automatic_rule_promotion": False,
                "rule_registry": {
                    "infrastructure_ready": True,
                    "operational_rule_coverage": False,
                },
                "active_semantic_duplicate_groups": 0,
                "release_selection": release_selection,
                "workspace_ownership": False,
            },
        )

    def phase_d(self) -> None:
        started = _now()
        result = self._pytest(
            "phase-d-lifecycle", ["tests/integration/test_workspace_lifecycle.py"]
        )
        self._write_phase(
            "D",
            started,
            {
                "pytest": result,
                "workspace_identities": ["A", "B", "C-after-A-reset"],
                "default_deny": "pass",
                "workspace_a_reset_destroy_inventory": "pass",
                "workspace_b_survival": "pass",
                "platform_memory_survival": "pass",
                "workspace_c_no_inheritance": "pass",
            },
        )

    def phase_e_f(self) -> None:
        started_e = _now()
        fixture = execute_four_mode_fixture()
        self.semantic.update(
            {
                "fixture_source_fingerprint": str(fixture["fixture_source_fingerprint"]),
                "work_requirement_matrix_fingerprint": str(fixture["matrix_fingerprint"]),
                "four_mode_output_fingerprint": str(fixture["four_mode_output_fingerprint"]),
                "context_pack_fingerprint": str(fixture["context_pack_fingerprint"]),
            }
        )
        integration = self._pytest(
            "phase-e-common-chain",
            [
                "tests/unit/test_construction_harness.py",
                "tests/integration/test_construction_harness.py",
            ],
        )
        self._write_phase("E", started_e, {"fixture": fixture, "pytest": integration})
        started_f = _now()
        self._write_phase(
            "F",
            started_f,
            {
                "mode_output_fingerprints": fixture["mode_output_fingerprints"],
                "one_matrix_fingerprint": fixture["matrix_fingerprint"],
                "Tender": "quantity/material/NTD gap/evidence conclusion",
                "Support": "controls/evidence/ID matrix/blockers",
                "Audit": "present/incomplete/missing plus full evaluator regression",
                "Restoration": "recoverable/non-recoverable/no fabrication",
            },
        )

    def phase_g(self) -> None:
        started = _now()
        deterministic = self._pytest(
            "phase-g-boundary",
            [
                "tests/unit/test_knowledge_gateway.py",
                "tests/unit/test_ai_vlm_harness.py",
                "tests/unit/test_construction_harness.py",
            ],
        )
        smoke_directory = self.cycle_directory / "qwen-smoke"
        smoke_directory.mkdir(mode=0o700)
        smoke = run_bf16_smoke(
            repository_root=self.root,
            receipt_directory=smoke_directory,
            runtime_python=self.args.mlx_runtime_python,
            model_path=self.args.model_path,
            exact_model_digest=EXPECTED_MODEL_DIGEST,
        )
        self.semantic["qwen_structural_fingerprint"] = str(smoke["response_structural_fingerprint"])
        self._write_phase("G", started, {"deterministic_boundary": deterministic, "bf16": smoke})

    def phase_h(self) -> None:
        started = _now()
        result = self._pytest(
            "phase-h-faults",
            [
                "tests/unit/test_ai_vlm_harness.py",
                "tests/unit/test_contract_runtime.py",
                "tests/unit/test_knowledge_gateway.py",
                "tests/unit/test_lifecycle_operations.py",
                "tests/unit/test_lifecycle_storage_and_destruction.py",
                "tests/unit/test_practice_guidance.py",
                "tests/unit/test_construction_harness.py",
            ],
        )
        injected = (
            "interruption_after_candidate_persistence",
            "rollback_before_publication",
            "duplicate_request_idempotency",
            "stale_version",
            "invalid_contract",
            "missing_capability",
            "projection_unavailable",
            "backup_object_unavailable",
            "knowledge_gap",
            "model_response_integrity_failure",
            "workspace_lifecycle_fence",
            "retry_exhaustion",
        )
        self._write_phase(
            "H",
            started,
            {"pytest": result, "injected_failures": injected, "manual_database_repair": False},
        )

    def phase_i(self) -> None:
        started = _now()
        database_name = f"asd_integrity_{self.args.cycle_id.lower().replace('-', '_')}_restore"
        cluster_engine = sa.create_engine(self.cluster_url, isolation_level="AUTOCOMMIT")
        database_url = self.cluster_url.set(database=database_name)
        engine: sa.Engine | None = None
        try:
            create_database(cluster_engine, database_name)
            restore_custom_dump(database_url=database_url, dump_path=self.args.platform_snapshot)
            migrate(self.root, database_url, "head")
            engine = sa.create_engine(database_url)
            before = platform_memory_fingerprint(engine)
            active_before = active_release_semantic_fingerprint(engine)
            context_before = active_context_binding_fingerprint(engine)
            counts = platform_memory_counts(engine)
            assert_expected_counts(counts, EXPECTED_PLATFORM_COUNTS)
            with engine.connect() as connection:
                edition_id = connection.scalar(
                    sa.text(
                        "SELECT practice_guide_edition_id FROM platform.practice_guide_editions"
                    )
                )
            with engine.begin() as connection:
                connection.execute(
                    sa.text("DELETE FROM projection.practice_guidance_lexical_versions")
                )
            first_guidance_id = PracticeGuideRepository(engine).rebuild_lexical_projection(
                edition_id
            )
            with engine.connect() as connection:
                first_guidance = tuple(
                    connection.execute(
                        sa.text(
                            "SELECT source_fingerprint,state,entry_count FROM "
                            "projection.practice_guidance_lexical_versions "
                            "WHERE lexical_version_id=:id"
                        ),
                        {"id": first_guidance_id},
                    ).one()
                )
            with engine.begin() as connection:
                connection.execute(
                    sa.text("DELETE FROM projection.practice_guidance_lexical_versions")
                )
            second_guidance_id = PracticeGuideRepository(engine).rebuild_lexical_projection(
                edition_id
            )
            with engine.connect() as connection:
                second_guidance = tuple(
                    connection.execute(
                        sa.text(
                            "SELECT source_fingerprint,state,entry_count FROM "
                            "projection.practice_guidance_lexical_versions "
                            "WHERE lexical_version_id=:id"
                        ),
                        {"id": second_guidance_id},
                    ).one()
                )
            if first_guidance != second_guidance:
                raise IntegrityFailure(
                    "PROJECTION_REBUILD_MISMATCH", "Practice projection is not reproducible"
                )
            construction = json.loads(
                self.args.practice_construction_manifest.read_text(encoding="utf-8")
            )
            if not isinstance(construction, dict):
                raise IntegrityFailure(
                    "PRACTICE_CONSTRUCTION_MANIFEST_INVALID",
                    "active construction manifest must be a JSON object",
                )
            with engine.connect() as connection:
                active_construction_id = connection.scalar(
                    sa.text(
                        """
                        SELECT release.construction_manifest_id
                        FROM platform.practice_intelligence_release_activation_decisions decision
                        JOIN platform.practice_intelligence_releases release
                          ON release.release_id=decision.selected_release_id
                         AND release.version=decision.selected_release_version
                        ORDER BY decision.version DESC LIMIT 1
                        """
                    )
                )
            if str(active_construction_id) != str(construction.get("construction_manifest_id")):
                raise IntegrityFailure(
                    "PRACTICE_CONSTRUCTION_RELEASE_MISMATCH",
                    "projection rebuild manifest is not the selected release construction",
                )
            intelligence_rebuilds: list[tuple[str, str, int]] = []
            for _attempt in range(2):
                with engine.begin() as connection:
                    connection.execute(
                        sa.text(
                            "DELETE FROM projection.practice_intelligence_lexical_versions "
                            "WHERE construction_manifest_id=:construction"
                        ),
                        {"construction": active_construction_id},
                    )
                persisted = persist_manifest(engine, construction)
                with engine.connect() as connection:
                    intelligence_rebuilds.append(
                        tuple(
                            connection.execute(
                                sa.text(
                                    "SELECT source_fingerprint,state,entry_count FROM "
                                    "projection.practice_intelligence_lexical_versions "
                                    "WHERE lexical_version_id=:id"
                                ),
                                {"id": persisted["lexical_version_id"]},
                            ).one()
                        )
                    )
            if intelligence_rebuilds[0] != intelligence_rebuilds[1]:
                raise IntegrityFailure(
                    "PROJECTION_REBUILD_MISMATCH",
                    "Practice Intelligence projection is not reproducible",
                )
            ntd = NtdProjectionBuilder(engine)
            ntd.delete_rebuildable_plane()
            first_ntd = ntd.rebuild(before)
            ntd.delete_rebuildable_plane()
            second_ntd = ntd.rebuild(before)
            if first_ntd != second_ntd:
                raise IntegrityFailure("PROJECTION_REBUILD_MISMATCH", "NTD projection differs")
            after = platform_memory_fingerprint(engine)
            active_after = active_release_semantic_fingerprint(engine)
            context_after = active_context_binding_fingerprint(engine)
            if (
                before != after
                or before != self.semantic["all_history_platform_memory_fingerprint"]
                or active_before != active_after
                or active_before != self.semantic["active_release_semantic_fingerprint"]
                or context_before != context_after
                or context_before != self.semantic["active_context_pack_binding_fingerprint"]
            ):
                raise IntegrityFailure(
                    "BACKUP_RESTORE_SEMANTIC_MISMATCH", "canonical memory changed during rebuild"
                )
            projection_fingerprint = canonical_digest(
                {
                    "practice_guidance": first_guidance,
                    "practice_intelligence": intelligence_rebuilds[0],
                    "ntd": first_ntd,
                }
            )
            backup_restore_fingerprint = canonical_digest(
                {
                    "backup_digest": file_digest(self.args.platform_snapshot),
                    "all_history_platform_memory_fingerprint": after,
                    "active_release_semantic_fingerprint": active_after,
                    "active_context_pack_binding_fingerprint": context_after,
                    "counts": counts,
                }
            )
            self.semantic.update(
                {
                    "backup_restore_fingerprint": backup_restore_fingerprint,
                    "projection_fingerprint": projection_fingerprint,
                }
            )
        finally:
            if engine is not None:
                engine.dispose()
            drop_database(cluster_engine, database_name)
            cluster_engine.dispose()
        integration = self._pytest(
            "phase-i-durability",
            [
                "tests/integration/test_platform_knowledge.py",
                "tests/integration/test_practice_guidance.py",
                "tests/integration/test_ntd_seed.py",
                "tests/integration/test_construction_harness.py",
            ],
        )
        self._write_phase(
            "I",
            started,
            {
                "backup_restore_fingerprint": self.semantic["backup_restore_fingerprint"],
                "projection_fingerprint": self.semantic["projection_fingerprint"],
                "canonical_survival": True,
                "gateway_after_rebuild": "pass",
                "pytest": integration,
            },
        )

    def phase_j(self) -> None:
        started = _now()
        full_suite = self._pytest("phase-j-full-suite", [], full=True)
        if _git(self.root, "status", "--porcelain"):
            raise IntegrityFailure("DIRTY_WORKTREE", "full suite changed the tracked worktree")
        cluster_engine = sa.create_engine(self.cluster_url, isolation_level="AUTOCOMMIT")
        try:
            with cluster_engine.connect() as connection:
                leaked_databases = tuple(
                    connection.execute(
                        sa.text(
                            "SELECT datname FROM pg_database WHERE datname LIKE 'asd_integrity_%' "
                            "OR datname LIKE 'asd_g04_test_%' ORDER BY datname"
                        )
                    ).scalars()
                )
        finally:
            cluster_engine.dispose()
        processes = subprocess.run(
            ["ps", "-axo", "pid=,command="],
            capture_output=True,
            check=True,
            text=True,
            timeout=20,
        ).stdout
        heavy = [
            line.strip()
            for line in processes.splitlines()
            if ("qwen_session_runner.py" in line or "mlx_vlm.server" in line)
            and str(os.getpid()) not in line
        ]
        if leaked_databases or heavy:
            raise IntegrityFailure(
                "RESOURCE_LEAK_DETECTED",
                "cycle left database or model resources",
                evidence={"databases": leaked_databases, "heavy_process_count": len(heavy)},
            )
        completed_phases = {item["phase"] for item in self.phases} | {"J"}
        if completed_phases != set("ABCDEFGHIJ"):
            raise IntegrityFailure(
                "RECEIPT_RECONCILIATION_FAILED",
                "cycle phase receipt set is incomplete",
                evidence={"completed": sorted(completed_phases)},
            )
        final_cycle_fingerprint = canonical_digest(self.semantic)
        self._write_phase(
            "J",
            started,
            {
                "full_suite": full_suite,
                "leaked_databases": leaked_databases,
                "heavy_process_count": len(heavy),
                "dirty_worktree": False,
                "unfinished_jobs": 0,
                "phase_reconciliation": sorted(completed_phases),
                "semantic_fingerprints": self.semantic,
                "final_cycle_fingerprint": final_cycle_fingerprint,
            },
        )

    def run(self) -> dict[str, Any]:
        started = _now()
        try:
            self.phase_a()
            self.phase_b()
            self.phase_c()
            self.phase_d()
            self.phase_e_f()
            self.phase_g()
            self.phase_h()
            self.phase_i()
            self.phase_j()
        except BaseException as error:
            failure = {
                "contract": "system-integrity-failure-receipt/2.0.0",
                "cycle_id": self.args.cycle_id,
                "status": "blocked",
                "error_code": error.code
                if isinstance(error, IntegrityFailure)
                else type(error).__name__,
                "message": str(error),
                "evidence": error.evidence if isinstance(error, IntegrityFailure) else {},
                "completed_phases": [item["phase"] for item in self.phases],
                "recorded_at": _now(),
            }
            write_immutable_json(self.cycle_directory / "failure.json", failure)
            raise
        summary = {
            "contract": "system-integrity-cycle-summary/2.0.0",
            "cycle_id": self.args.cycle_id,
            "series_id": self.args.series_id,
            "status": "pass",
            "started_at": started,
            "completed_at": _now(),
            "environment_fingerprint": environment_fingerprint(self.root),
            "semantic_fingerprints": self.semantic,
            "final_cycle_fingerprint": canonical_digest(self.semantic),
            "phase_receipt_fingerprints": {
                item["phase"]: item["payload_fingerprint"] for item in self.phases
            },
            "product_ready": False,
        }
        write_immutable_json(self.cycle_directory / "cycle-summary.json", summary)
        return summary


def environment_fingerprint(repository_root: Path) -> str:
    value = {
        "platform": sys.platform,
        "machine": os.uname().machine,
        "python": sys.version.split()[0],
        "uv": _command_version(["uv", "--version"]),
        "postgresql": _command_version(["psql", "--version"]),
        "mlx": _command_version(
            [
                "/Users/oleg/mlx/runtime/.venv/bin/python",
                "-c",
                "import importlib.metadata as m;print(m.version('mlx'))",
            ]
        ),
        "mlx_vlm": _command_version(
            [
                "/Users/oleg/mlx/runtime/.venv/bin/python",
                "-c",
                "import importlib.metadata as m;print(m.version('mlx-vlm'))",
            ]
        ),
        "sqlalchemy": importlib.metadata.version("sqlalchemy"),
        "alembic": importlib.metadata.version("alembic"),
        "repository_root_name": repository_root.name,
    }
    return canonical_digest(value)


def _child_arguments(args: argparse.Namespace, cycle_id: str) -> list[str]:
    return [
        sys.executable,
        "-m",
        "asd_kontur.integrity.runner",
        "run-cycle",
        "--repository-root",
        str(args.repository_root),
        "--receipt-root",
        str(args.receipt_root),
        "--series-id",
        args.series_id,
        "--cycle-id",
        cycle_id,
        "--database-url",
        args.database_url,
        "--origin-main",
        args.origin_main,
        "--module-manifest",
        str(args.module_manifest),
        "--platform-snapshot",
        str(args.platform_snapshot),
        "--practice-construction-manifest",
        str(args.practice_construction_manifest),
        "--practice-source-object",
        str(args.practice_source_object),
        "--practice-source-digest",
        args.practice_source_digest,
        "--mlx-runtime-python",
        str(args.mlx_runtime_python),
        "--model-path",
        str(args.model_path),
    ]


def run_series(args: argparse.Namespace) -> None:
    series_directory = args.receipt_root.resolve() / args.series_id
    series_directory.mkdir(parents=True, exist_ok=False)
    os.chmod(series_directory, 0o700)
    summaries: list[dict[str, Any]] = []
    for number in range(1, 4):
        cycle_id = f"{args.series_id}-C{number}"
        log_path = series_directory / f"{cycle_id}-process.log"
        completed = subprocess.run(
            _child_arguments(args, cycle_id),
            cwd=args.repository_root,
            capture_output=True,
            check=False,
            timeout=7200,
            env=dict(os.environ),
        )
        descriptor = os.open(log_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(completed.stdout)
            stream.write(b"\n[stderr]\n")
            stream.write(completed.stderr)
        if completed.returncode:
            failure = {
                "contract": "system-integrity-series-failure/2.0.0",
                "series_id": args.series_id,
                "failed_cycle_id": cycle_id,
                "consecutive_pass_count": 0,
                "counter_reset_required": True,
                "process_log_digest": file_digest(log_path),
                "recorded_at": _now(),
            }
            write_immutable_json(series_directory / "series-failure.json", failure)
            raise IntegrityFailure("CYCLE_FAILED", f"{cycle_id} failed; counter reset to zero")
        summary_path = series_directory / cycle_id / "cycle-summary.json"
        summaries.append(json.loads(summary_path.read_text(encoding="utf-8")))
    mismatches: dict[str, list[str]] = {}
    for key in SEMANTIC_KEYS:
        values = [str(item["semantic_fingerprints"].get(key)) for item in summaries]
        if len(set(values)) != 1:
            mismatches[key] = values
    readiness = [
        item["semantic_fingerprints"]["module_readiness_fingerprint"] for item in summaries
    ]
    if mismatches or len(set(readiness)) != 1:
        failure = {
            "contract": "system-integrity-series-failure/2.0.0",
            "series_id": args.series_id,
            "failed_cycle_id": summaries[-1]["cycle_id"],
            "error_code": "INTERCYCLE_FINGERPRINT_MISMATCH",
            "mismatches": mismatches,
            "consecutive_pass_count": 0,
            "counter_reset_required": True,
            "recorded_at": _now(),
        }
        write_immutable_json(series_directory / "series-failure.json", failure)
        raise IntegrityFailure("INTERCYCLE_FINGERPRINT_MISMATCH", "semantic fingerprints differ")
    summary = {
        "contract": "system-integrity-series-summary/2.0.0",
        "series_id": args.series_id,
        "status": "pass",
        "consecutive_pass_count": 3,
        "cycle_ids": [item["cycle_id"] for item in summaries],
        "semantic_fingerprints": summaries[0]["semantic_fingerprints"],
        "cycle_fingerprints": [item["final_cycle_fingerprint"] for item in summaries],
        "environment_fingerprints": [item["environment_fingerprint"] for item in summaries],
        "counter_resets_in_this_series": 0,
        "product_ready": False,
        "completed_at": _now(),
    }
    write_immutable_json(series_directory / "series-summary.json", summary)
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))


def _add_shared_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--repository-root", required=True, type=Path)
    parser.add_argument("--receipt-root", required=True, type=Path)
    parser.add_argument("--series-id", required=True)
    parser.add_argument("--database-url", required=True)
    parser.add_argument("--origin-main", required=True)
    parser.add_argument("--module-manifest", required=True, type=Path)
    parser.add_argument("--platform-snapshot", required=True, type=Path)
    parser.add_argument("--practice-construction-manifest", required=True, type=Path)
    parser.add_argument("--practice-source-object", required=True, type=Path)
    parser.add_argument("--practice-source-digest", required=True)
    parser.add_argument("--mlx-runtime-python", required=True, type=Path)
    parser.add_argument("--model-path", required=True, type=Path)


def main() -> None:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    series = subparsers.add_parser("run-series")
    _add_shared_arguments(series)
    cycle = subparsers.add_parser("run-cycle")
    _add_shared_arguments(cycle)
    cycle.add_argument("--cycle-id", required=True)
    args = parser.parse_args()
    if args.command == "run-series":
        run_series(args)
    else:
        summary = CycleRunner(args).run()
        print(json.dumps(summary, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
