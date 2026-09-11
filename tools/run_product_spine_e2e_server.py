"""Run a disposable PostgreSQL-backed Product Spine for browser E2E only."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import tempfile
from argparse import Namespace
from datetime import UTC, date, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from types import SimpleNamespace
from uuid import UUID

import sqlalchemy as sa
import uvicorn
from alembic import command
from alembic.config import Config
from sqlalchemy.engine import URL, make_url

from asd_kontur.application_spine.auth import OwnerAuthService
from asd_kontur.application_spine.config import SessionProfile, SpineSettings
from asd_kontur.domain import deterministic_uuid
from asd_kontur.knowledge.postgres import RuleRegistryService
from asd_kontur.knowledge.rules import AuthorityIdentity, RuleState
from asd_kontur.ntd.models import NormativeActivationDecision
from asd_kontur.ntd.postgres import NtdRepository
from asd_kontur.ntd.rules import (
    DeonticType,
    NormativeRuleCandidate,
    RuleQualificationDecision,
    RuleQualificationStatus,
    SemanticEvidenceBinding,
    decide_rule_activation,
)
from asd_kontur.web_app import create_app

SYNTHETIC_QWEN_ANSWER = "Synthetic CI model response: dialog persistence verified."


def _start_synthetic_qwen() -> ThreadingHTTPServer:
    """Provide only the model transport; API, Gateway and history remain real."""

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            length = int(self.headers.get("Content-Length", "0"))
            if self.path != "/generate" or not 0 < length <= 128_000:
                self.send_error(400)
                return
            payload = json.loads(self.rfile.read(length))
            if not isinstance(payload.get("prompt"), str) or not payload["prompt"]:
                self.send_error(400)
                return
            body = (
                json.dumps({"event": "delta", "text": SYNTHETIC_QWEN_ANSWER})
                + "\n"
                + json.dumps({"event": "completed"})
                + "\n"
            ).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/x-ndjson")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args: object) -> None:
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    Thread(target=server.serve_forever, daemon=True).start()
    return server


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


def _database_identifier(name: str) -> str:
    if re.fullmatch(r"[a-z0-9_]+", name) is None:
        raise RuntimeError("E2E template database name is invalid")
    return name


def _seed_active_rule_path(engine: sa.Engine) -> None:
    """Exercise the human-authorized active path only in a disposable E2E clone."""

    with engine.connect() as connection:
        row = dict(
            connection.execute(
                sa.text(
                    "SELECT c.*,q.qualification_decision_id,q.version qualification_version,"
                    "q.status qualification_status,q.gate_results,q.qualification_profile_version,"
                    "q.test_manifest_digest,q.decision_fingerprint qualification_fingerprint,"
                    "o.rule_version_id,e.normative_document_id FROM "
                    "platform.normative_rule_candidates c JOIN "
                    "platform.normative_rule_qualification_decisions q ON "
                    "q.normative_rule_candidate_id=c.normative_rule_candidate_id AND "
                    "q.normative_rule_candidate_version=c.version JOIN "
                    "platform.normative_rule_activation_outcomes o ON "
                    "o.normative_rule_candidate_id=c.normative_rule_candidate_id AND "
                    "o.normative_rule_candidate_version=c.version JOIN "
                    "platform.normative_editions e "
                    "ON e.normative_edition_id=c.normative_edition_id WHERE "
                    "c.structural_path='10.8' ORDER BY q.decided_at DESC,o.decided_at DESC LIMIT 1"
                )
            )
            .mappings()
            .one()
        )
    now = datetime.now(UTC)
    repository = NtdRepository(engine)
    edition_decision_id = deterministic_uuid(
        f"synthetic-e2e-edition-activation:{row['normative_edition_id']}"
    )
    repository.record_activation(
        NormativeActivationDecision(
            edition_decision_id,
            1,
            UUID(str(row["normative_document_id"])),
            UUID(str(row["normative_edition_id"])),
            date(2026, 8, 26),
            "active",
            "synthetic-e2e:independent-edition-authority",
            ("synthetic-e2e:official-edition-evidence",),
            None,
            now,
        )
    )
    registry = RuleRegistryService(engine)
    rule_version_id = UUID(str(row["rule_version_id"]))
    reviewer = AuthorityIdentity("human.synthetic-e2e.rule-reviewer", "human")
    approver = AuthorityIdentity(
        "human.synthetic-e2e.rule-approver", "human", frozenset({"rule.approve"})
    )
    registry.transition(
        rule_version_id=rule_version_id,
        target=RuleState.REVIEWED,
        actor=reviewer,
        decision_ref="synthetic-e2e:review",
        qualification_ref="synthetic-e2e:reviewer-qualification",
        test_manifest_digest=str(row["test_manifest_digest"]),
    )
    registry.transition(
        rule_version_id=rule_version_id,
        target=RuleState.APPROVED,
        actor=approver,
        decision_ref="synthetic-e2e:approval",
        qualification_ref="synthetic-e2e:approver-qualification",
    )
    registry.transition(
        rule_version_id=rule_version_id,
        target=RuleState.ACTIVE,
        actor=approver,
        decision_ref="synthetic-e2e:activation",
    )
    bindings = tuple(
        SemanticEvidenceBinding(str(item["field"]), tuple(item["source_quotes"]))
        for item in row["semantic_evidence_bindings"]
    )
    candidate = NormativeRuleCandidate(
        UUID(str(row["normative_rule_candidate_id"])),
        int(row["version"]),
        UUID(str(row["normative_document_id"])),
        UUID(str(row["normative_edition_id"])),
        UUID(str(row["source_version_id"])),
        UUID(str(row["normative_provision_id"])),
        int(row["normative_provision_version"]),
        UUID(str(row["source_locator_id"])),
        str(row["structural_path"]),
        str(row["verbatim_text"]),
        str(row["verbatim_digest"]),
        DeonticType(str(row["deontic_type"])),
        dict(row["actor"]),
        dict(row["regulated_object"]),
        dict(row["required_action"]),
        dict(row["applicability_predicate"]),
        tuple(row["conditions"]),
        tuple(row["exceptions"]),
        dict(row["output_contract"]),
        bindings,
        str(row["interpretation_profile_version"]),
        str(row["semantic_fingerprint"]),
    )
    qualification = RuleQualificationDecision(
        UUID(str(row["qualification_decision_id"])),
        int(row["qualification_version"]),
        candidate.candidate_id,
        candidate.version,
        RuleQualificationStatus(str(row["qualification_status"])),
        tuple(tuple(value) for value in row["gate_results"]),
        str(row["qualification_profile_version"]),
        str(row["test_manifest_digest"]),
        str(row["qualification_fingerprint"]),
    )
    activation = decide_rule_activation(
        candidate,
        qualification,
        edition_activation_status="active",
        rule_lifecycle_status="active",
    )
    repository.record_rule_activation_outcome(
        activation,
        rule_version_id=rule_version_id,
        edition_activation_decision=(edition_decision_id, 1),
        authority_identity_id=approver.identity_id,
        authority_decision_ref="synthetic-e2e:activation",
        decided_at=now,
    )


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
    qwen_server: ThreadingHTTPServer | None = None
    try:
        template_database = os.environ.get("ASD_E2E_TEMPLATE_DATABASE")
        with cluster.begin() as connection:
            if template_database:
                template = _database_identifier(template_database)
                connection.exec_driver_sql(
                    f'CREATE DATABASE "{database_name}" TEMPLATE "{template}"'
                )
            else:
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
        template_owner_mode = os.environ.get("ASD_E2E_TEMPLATE_OWNER_MODE") == "1"
        role_urls = (
            {name: database_url for name in roles}
            if template_owner_mode
            else {
                name: database_url.set(username=role, password=password)
                for name, role in roles.items()
            }
        )
        objects = runtime_root / "objects"
        archives = runtime_root / "archives"
        objects.mkdir()
        archives.mkdir()
        if os.environ.get("ASD_E2E_SYNTHETIC_QWEN") == "1":
            if os.environ.get("ASD_E2E_EXPECT_CONSULTANT_CITATIONS") == "1":
                raise RuntimeError("Synthetic model cannot qualify real-Qwen citation acceptance")
            qwen_server = _start_synthetic_qwen()
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
            ntd_embedding_endpoint=os.environ.get("ASD_NTD_EMBEDDING_ENDPOINT") or None,
            qwen_bind_port=(
                qwen_server.server_port
                if qwen_server is not None
                else int(os.environ.get("ASD_QWEN_BIND_PORT", "8790"))
            ),
        )
        app_engine = sa.create_engine(settings.database_url, pool_pre_ping=True)
        if os.environ.get("ASD_E2E_SEED_ACTIVE_RULE") == "1":
            _seed_active_rule_path(app_engine)
        OwnerAuthService(app_engine, settings).bootstrap_owner(
            username="synthetic-live-owner",
            password="Synthetic-Live-Owner-Password-42!",
            display_name="Synthetic live owner",
        )
        support_workspace_id: str | None = None
        if os.environ.get("ASD_E2E_SEED_SUPPORT_PRODUCTION") == "1":
            support_workspace_id = _seed_support_production_path(
                database_url=database_url,
                runtime_root=runtime_root,
                object_store_root=objects,
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
                    "support_workspace_id": support_workspace_id,
                    "synthetic_qwen_answer": (
                        SYNTHETIC_QWEN_ANSWER if qwen_server is not None else None
                    ),
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
        if qwen_server is not None:
            qwen_server.shutdown()
            qwen_server.server_close()
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


def _seed_support_production_path(
    *, database_url: URL, runtime_root: Path, object_store_root: Path
) -> str:
    """Reuse the fully asserted synthetic acceptance chain for live browser seeding."""

    from tests.integration.test_support_production_id import (
        test_support_production_package_generation_and_workspace_isolation,
    )

    owner_engine = sa.create_engine(database_url, pool_pre_ping=True)
    seed_root = runtime_root / "support-production-seed"
    seed_root.mkdir()
    environment = SimpleNamespace(
        cluster_admin_url=database_url,
        owner_engine=owner_engine,
        application_engine=owner_engine,
        lifecycle_engine=owner_engine,
        destruction_engine=owner_engine,
        document_worker_engine=owner_engine,
        kernel_engine=owner_engine,
        harness_engine=owner_engine,
        support_engine=owner_engine,
    )
    try:
        os.environ["ASD_SUPPORT_PRODUCTION_PRESERVE_WORKSPACE"] = "1"
        try:
            test_support_production_package_generation_and_workspace_isolation(
                environment, seed_root
            )
        finally:
            os.environ.pop("ASD_SUPPORT_PRODUCTION_PRESERVE_WORKSPACE", None)
        shutil.copytree(seed_root / "objects", object_store_root, dirs_exist_ok=True)
        owner_identity = "owner:" + hashlib.sha256(b"synthetic-product-owner").hexdigest()[:24]
        with owner_engine.connect() as connection:
            workspace_id = connection.scalar(
                sa.text(
                    "SELECT w.workspace_id FROM workspace.workspaces w JOIN "
                    "application.owner_organization_grants g ON "
                    "g.organization_id=w.organization_id "
                    "WHERE g.owner_identity_id=:owner AND w.lifecycle_state='ACTIVE' "
                    "ORDER BY w.created_at LIMIT 1"
                ),
                {"owner": owner_identity},
            )
        if workspace_id is None:
            raise RuntimeError("support production E2E workspace was not materialized")
        return str(workspace_id)
    finally:
        owner_engine.dispose()


if __name__ == "__main__":
    main()
