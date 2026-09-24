# ruff: noqa: RUF001 - fixtures preserve Russian construction terminology.

from __future__ import annotations

import io
import json
import os
import runpy
import time
import zipfile
from dataclasses import replace
from pathlib import Path
from uuid import UUID

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient

from asd_kontur.application_spine.config import SessionProfile, SpineSettings
from asd_kontur.application_spine.object_store import WorkspaceObjectStore
from asd_kontur.application_spine.postgres import SpinePostgresRepository
from asd_kontur.application_spine.worker import DocumentWorker, WorkerOutcome
from asd_kontur.assistant.gateway import ProfessionalAssistantKnowledgeQuery
from asd_kontur.document_understanding.postgres import IndustrialUnderstandingRepository
from asd_kontur.domain import uuid7
from asd_kontur.knowledge.gateway import GatewayContext
from asd_kontur.persistence import WorkspaceContext, WorkspaceUnitOfWork
from asd_kontur.support.scope_commands import (
    SupportScopeCommandError,
    SupportScopeCommandService,
    SupportScopeConfiguration,
)
from asd_kontur.web_app import create_app

from .conftest import PostgreSQLEnvironment
from .test_common_domain_kernel import _seed_rule
from .test_workspace_lifecycle import Tenant

pytestmark = pytest.mark.postgres


def _drain_worker_through_bounded_retries(
    worker: DocumentWorker, *, timeout_seconds: float = 8.0
) -> tuple[list[WorkerOutcome], dict[str, str]]:
    """Exercise scheduled retries and return each job's effective observed state."""

    outcomes: list[WorkerOutcome] = []
    latest_states: dict[str, str] = {}
    deadline = time.monotonic() + timeout_seconds
    while True:
        outcome = worker.run_once()
        if outcome is not None:
            outcomes.append(outcome)
            latest_states[outcome.job_id] = outcome.state.value
            continue
        if "queued" not in latest_states.values():
            return outcomes, latest_states
        if time.monotonic() >= deadline:
            pytest.fail(f"worker_retry_did_not_settle:{latest_states}")
        time.sleep(0.1)


def _build_synthetic_corpus(root: Path) -> dict[str, object]:
    namespace = runpy.run_path(
        str(
            Path(__file__).resolve().parents[2]
            / "tools/build_industrial_intake_synthetic_corpus.py"
        )
    )
    return namespace["build"](root)  # type: ignore[no-any-return,operator]


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
        audit_pepper="synthetic-industrial-understanding-audit-pepper",
        max_file_bytes=4 * 1024 * 1024,
        max_batch_bytes=8 * 1024 * 1024,
    )


def _docx() -> bytes:
    body = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:body>
    <w:p><w:r><w:t>Пояснительная записка</w:t></w:r></w:p>
    <w:p><w:r><w:t>Наименование объекта: Производственный корпус</w:t></w:r></w:p>
    <w:p><w:r><w:t>Назначение объекта: Выпуск строительных материалов</w:t></w:r></w:p>
    <w:p><w:r><w:t>Состав объекта: Корпус; наружная тепловая сеть</w:t></w:r></w:p>
  </w:body>
</w:document>"""
    target = io.BytesIO()
    with zipfile.ZipFile(target, "w") as archive:
        archive.writestr("[Content_Types].xml", "<Types/>")
        archive.writestr("word/document.xml", body)
    return target.getvalue()


def _support_qwen_qualification_docx() -> bytes:
    """One controlled free-text case whose expected engineering values are fixed here."""

    body = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/'
        'wordprocessingml/2006/main"><w:body>'
        "<w:p><w:r><w:t>Квалификационная пояснительная записка</w:t></w:r></w:p>"
        "<w:p><w:r><w:t>На участке У-01 предусмотрено устройство монолитной "
        "железобетонной фундаментной плиты объёмом 18,4 м³ из бетона класса В25."
        "</w:t></w:r></w:p><w:p><w:r><w:t>Работы выполняются по синтетическому "
        "листу КЖ-7 редакции 2. Исполнительные даты, результаты лабораторных "
        "испытаний и подписи в источнике отсутствуют.</w:t></w:r></w:p>"
        "</w:body></w:document>"
    )
    target = io.BytesIO()
    with zipfile.ZipFile(target, "w") as archive:
        archive.writestr("[Content_Types].xml", "<Types/>")
        archive.writestr("word/document.xml", body)
    return target.getvalue()


def _vor_csv() -> bytes:
    return (
        "Ведомость объёмов работ;;;;;\n"
        "Вид работ;Объём;Ед. изм.;Материал;Количество материала;Ед. изм. материала\n"
        "Устройство монолитной плиты;+12,350;м³;Бетон В25;12,350;м³\n"
    ).encode()


def _login(
    client: TestClient,
    *,
    username: str = "understanding-owner",
    password: str = "Synthetic-Owner-Password-42!",
) -> dict[str, str]:
    response = client.post(
        "/api/v1/session/login",
        json={"username": username, "password": password},
    )
    assert response.status_code == 200
    csrf = client.cookies.get("asd_csrf")
    assert csrf
    return {"X-CSRF-Token": csrf}


def _seed_verified_work_type_catalog(environment: PostgreSQLEnvironment) -> tuple[UUID, UUID]:
    work_type_id = UUID("71000000-0000-4000-8000-000000000001")
    catalog_id = UUID("72000000-0000-4000-8000-000000000001")
    with environment.owner_engine.begin() as connection:
        connection.execute(
            sa.text(
                "INSERT INTO platform.work_types (work_type_id,work_type_key,"
                "identity_namespace_version,created_by_identity_id) VALUES "
                "(:work,'concrete.slab.install','synthetic-catalog-v1','test:catalog-owner')"
            ),
            {"work": work_type_id},
        )
        connection.execute(
            sa.text(
                "INSERT INTO platform.work_type_versions (work_type_id,version,taxonomy_version,"
                "title,status,evidence_manifest_digest,integrity_digest) VALUES "
                "(:work,'1.0.0','synthetic-taxonomy-v1','Устройство монолитной плиты','active',"
                ":evidence,:integrity)"
            ),
            {
                "work": work_type_id,
                "evidence": "sha256:" + "7" * 64,
                "integrity": "sha256:" + "8" * 64,
            },
        )
        connection.execute(
            sa.text(
                "INSERT INTO platform.work_type_catalog_versions "
                "(catalog_id,version,source_identity,source_version,source_digest,provenance,status,"
                "catalog_fingerprint) VALUES (:catalog,1,'synthetic-known-catalog','1.0.0',:source,"
                "CAST(:provenance AS jsonb),'verified',:fingerprint)"
            ),
            {
                "catalog": catalog_id,
                "source": "sha256:" + "9" * 64,
                "provenance": json.dumps({"fixture": "known-work-type"}),
                "fingerprint": "sha256:" + "a" * 64,
            },
        )
        connection.execute(
            sa.text(
                "INSERT INTO platform.work_type_catalog_entries "
                "(catalog_id,catalog_version,work_type_id,stable_key,printed_name,normalized_name,"
                "aliases,parent_work_type_id,applicability,state,provenance,semantic_digest) "
                "VALUES "
                "(:catalog,1,:work,'concrete.slab.install','Устройство монолитной плиты',"
                "'устройство монолитной плиты',"
                "ARRAY['устройство монолитной железобетонной фундаментной плиты']::text[],"
                "NULL,CAST('{}' AS jsonb),"
                "'effective',"
                "CAST(:provenance AS jsonb),:digest)"
            ),
            {
                "catalog": catalog_id,
                "work": work_type_id,
                "provenance": json.dumps({"fixture": "known-work-type"}),
                "digest": "sha256:" + "b" * 64,
            },
        )
    return work_type_id, catalog_id


def test_tender_contract_analysis_is_scoped_and_honest_when_not_started(
    postgres_environment: PostgreSQLEnvironment,
    tmp_path: Path,
) -> None:
    """The Tender surface must not fabricate a contract review or cross scopes."""

    settings = _settings(postgres_environment, tmp_path)
    app = create_app(engine=postgres_environment.application_engine, settings=settings)
    app.state.container.auth.bootstrap_owner(
        username="contract-analysis-owner",
        password="Synthetic-Contract-Owner-Password-42!",
        display_name="Synthetic contract-analysis owner",
    )
    app.state.container.auth.bootstrap_owner(
        username="contract-analysis-other",
        password="Synthetic-Contract-Other-Password-42!",
        display_name="Synthetic contract-analysis other owner",
    )
    with TestClient(app) as owner, TestClient(app) as other:
        owner_csrf = _login(
            owner,
            username="contract-analysis-owner",
            password="Synthetic-Contract-Owner-Password-42!",
        )
        other_csrf = _login(
            other,
            username="contract-analysis-other",
            password="Synthetic-Contract-Other-Password-42!",
        )
        workspace = owner.post(
            "/api/v1/workspaces",
            json={"display_name": "Contract analysis scope"},
            headers=owner_csrf,
        )
        assert workspace.status_code == 201, workspace.text
        workspace_id = workspace.json()["workspace_id"]

        response = owner.get(f"/api/v1/workspaces/{workspace_id}/tender/contract-analysis")
        assert response.status_code == 200, response.text
        value = response.json()
        assert value == {
            "status": "not_started",
            "process": None,
            "assessment": None,
            "clauses": [],
            "issues": [],
            "protocols": [],
            "disagreement_items": [],
            "revised_contracts": [],
            "revised_clauses": [],
            "deliverables": [],
            "gaps": ["TENDER_CONTRACT_PROCESS_NOT_STARTED"],
            "authority_boundary": "read_only_projection",
        }

        hidden = other.get(f"/api/v1/workspaces/{workspace_id}/tender/contract-analysis")
        assert hidden.status_code == 404, hidden.text
        assert hidden.json()["error"]["code"] == "workspace_not_found"
        exported = owner.get(f"/api/v1/workspaces/{workspace_id}/tender/contract-analysis.csv")
        assert exported.status_code == 200, exported.text
        assert exported.headers["content-type"] == "text/csv; charset=utf-8"
        assert "TENDER_CONTRACT_PROCESS_NOT_STARTED" in exported.content.decode("utf-8-sig")
        report = owner.get(f"/api/v1/workspaces/{workspace_id}/tender/contract-analysis.docx")
        assert report.status_code == 200, report.text
        assert report.headers["content-type"] == (
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        )
        with zipfile.ZipFile(io.BytesIO(report.content)) as package:
            report_xml = package.read("word/document.xml").decode("utf-8")
        assert "Договорный Tender-процесс не сформирован" in report_xml
        assert "TENDER_CONTRACT_PROCESS_NOT_STARTED" in report_xml
        hidden_export = other.get(f"/api/v1/workspaces/{workspace_id}/tender/contract-analysis.csv")
        assert hidden_export.status_code == 404, hidden_export.text
        hidden_report = other.get(
            f"/api/v1/workspaces/{workspace_id}/tender/contract-analysis.docx"
        )
        assert hidden_report.status_code == 404, hidden_report.text
        assert other_csrf["X-CSRF-Token"]


def test_authorized_support_scope_configuration_is_idempotent_and_owner_scoped(
    postgres_environment: PostgreSQLEnvironment,
    tmp_path: Path,
) -> None:
    """A configured professional scope unlocks the existing ID-package path."""

    settings = replace(
        _settings(postgres_environment, tmp_path),
        support_command_database_url=_database_url(postgres_environment.support_engine),
    )
    app = create_app(engine=postgres_environment.application_engine, settings=settings)
    owner_identity_id = app.state.container.auth.bootstrap_owner(
        username="support-scope-owner",
        password="Synthetic-Support-Scope-Owner-Password-42!",
        display_name="Synthetic Support scope owner",
    )
    app.state.container.auth.bootstrap_owner(
        username="support-scope-other",
        password="Synthetic-Support-Scope-Other-Password-42!",
        display_name="Synthetic Support scope other owner",
    )
    with TestClient(app) as client, TestClient(app) as other:
        csrf = _login(
            client,
            username="support-scope-owner",
            password="Synthetic-Support-Scope-Owner-Password-42!",
        )
        workspace_response = client.post(
            "/api/v1/workspaces",
            json={"display_name": "Support scope command"},
            headers=csrf,
        )
        assert workspace_response.status_code == 201, workspace_response.text
        workspace = workspace_response.json()
        organization_id = UUID(workspace["organization_id"])
        workspace_id = UUID(workspace["workspace_id"])
        tenant = Tenant(
            organization_id,
            UUID(workspace["construction_object_id"]),
            workspace_id,
        )
        mode_execution_id = uuid7()
        with WorkspaceUnitOfWork(
            postgres_environment.application_engine,
            WorkspaceContext(
                organization_id,
                workspace_id,
                owner_identity_id,
                "service.synthetic-support-scope-test",
                uuid7(),
            ),
        ) as unit:
            assert unit.workspaces is not None
            unit.workspaces.create_mode_execution(
                mode_execution_id=mode_execution_id,
                mode="Support",
                purpose="purpose.synthetic.support-scope",
                input_manifest_ref="manifest.synthetic.support-scope",
                policy_assignment_key="policy.synthetic",
                policy_assignment_version="0.1.0",
                rule_set_key="rules.synthetic",
                rule_set_version="0.1.0",
            )
        rule_set_version_id, _, _, _ = _seed_rule(postgres_environment, tenant)
        grant_id = uuid7()
        with postgres_environment.owner_engine.begin() as connection:
            connection.execute(
                sa.text(
                    "INSERT INTO workspace.support_professional_grants "
                    "(organization_id,workspace_id,grant_id,grant_version,human_identity_id,"
                    "capability,professional_qualification_ref,authority_reference,status,"
                    "effective_from,integrity_digest) "
                    "VALUES (:o,:w,:grant,1,:owner,"
                    "'support.scope.configure','qualification:synthetic-support@1',"
                    "'authority:synthetic-support@1','active',CURRENT_TIMESTAMP,:digest)"
                ),
                {
                    "o": organization_id,
                    "w": workspace_id,
                    "grant": grant_id,
                    "owner": owner_identity_id,
                    "digest": "sha256:" + "b" * 64,
                },
            )
        upload = client.post(
            f"/api/v1/workspaces/{workspace_id}/documents",
            files=[("files", ("scope-source.docx", _docx(), "application/octet-stream"))],
            headers=csrf,
        )
        assert upload.status_code == 202, upload.text
        with postgres_environment.owner_engine.connect() as connection:
            manifest_digest = connection.scalar(
                sa.text(
                    "SELECT manifest_digest FROM workspace.intake_manifests "
                    "WHERE organization_id=:o "
                    "AND workspace_id=:w ORDER BY created_at DESC LIMIT 1"
                ),
                {"o": organization_id, "w": workspace_id},
            )
        assert isinstance(manifest_digest, str)
        readiness = client.get(f"/api/v1/workspaces/{workspace_id}/support/scope-readiness")
        assert readiness.status_code == 200, readiness.text
        assert readiness.json()["status"] == "ready"
        assert readiness.json()["gaps"] == []
        payload = readiness.json()["configuration"]
        assert payload["mode_execution_id"] == str(mode_execution_id)
        assert payload["rule_set_version_id"] == str(rule_set_version_id)
        assert payload["input_manifest_digest"] == manifest_digest
        assert payload["professional_grant_id"] == str(grant_id)
        assert payload["professional_qualification_ref"] == ("qualification:synthetic-support@1")
        tampered_contract = client.post(
            f"/api/v1/workspaces/{workspace_id}/support/processes",
            json={
                **payload,
                "rule_set_version_id": str(uuid7()),
                "idempotency_key": "support-scope-tampered-contract-01",
            },
            headers=csrf,
        )
        assert tampered_contract.status_code == 409, tampered_contract.text
        assert tampered_contract.json()["error"]["code"] == ("support_scope_contract_mismatch")
        first = client.post(
            f"/api/v1/workspaces/{workspace_id}/support/processes",
            json=payload,
            headers=csrf,
        )
        second = client.post(
            f"/api/v1/workspaces/{workspace_id}/support/processes",
            json=payload,
            headers=csrf,
        )
        assert first.status_code == second.status_code == 201
        assert first.json()["outcome"] == "accepted_completed"
        assert second.json()["outcome"] == "duplicate_completed"
        assert first.json()["support_process_id"] == second.json()["support_process_id"]
        assert first.json()["revision"] == second.json()["revision"] == 1
        assert first.json()["state"] == "scope_configured"
        configured = client.get(f"/api/v1/workspaces/{workspace_id}/support/scope-readiness")
        assert configured.status_code == 200, configured.text
        assert configured.json() == {
            "status": "configured",
            "gaps": [],
            "configuration": None,
        }
        conflicting = client.post(
            f"/api/v1/workspaces/{workspace_id}/support/processes",
            json={**payload, "purpose": "changed semantic Support scope"},
            headers=csrf,
        )
        assert conflicting.status_code == 409, conflicting.text
        assert conflicting.json()["error"]["code"] == "SUPPORT_IDEMPOTENCY_CONFLICT"
        missing_manifest = client.post(
            f"/api/v1/workspaces/{workspace_id}/support/processes",
            json={
                **payload,
                "input_manifest_digest": "sha256:" + "f" * 64,
                "idempotency_key": "support-scope-configuration-missing-manifest-01",
            },
            headers=csrf,
        )
        assert missing_manifest.status_code == 404, missing_manifest.text
        assert missing_manifest.json()["error"]["code"] == "support_input_manifest_not_found"
        with pytest.raises(SupportScopeCommandError, match="support_command_role_invalid"):
            SupportScopeCommandService(
                postgres_environment.application_engine,
                postgres_environment.application_engine,
            ).configure(
                owner_identity_id=owner_identity_id,
                workspace_id=workspace_id,
                correlation_id=uuid7(),
                configuration=SupportScopeConfiguration(
                    mode_execution_id=UUID(payload["mode_execution_id"]),
                    rule_set_version_id=UUID(payload["rule_set_version_id"]),
                    process_definition_version=payload["process_definition_version"],
                    authority_profile_version=payload["authority_profile_version"],
                    contract_registry_version=payload["contract_registry_version"],
                    policy_versions=tuple(payload["policy_versions"]),
                    deliverable_scope=tuple(payload["deliverable_scope"]),
                    classification=payload["classification"],
                    purpose="wrong writer role must fail closed",
                    source_class_allowlist=tuple(payload["source_class_allowlist"]),
                    input_manifest_digest=payload["input_manifest_digest"],
                    professional_grant_id=UUID(payload["professional_grant_id"]),
                    professional_grant_version=payload["professional_grant_version"],
                    professional_qualification_ref=payload["professional_qualification_ref"],
                    idempotency_key="support-scope-configuration-wrong-role-01",
                ),
            )
        production = client.get(f"/api/v1/workspaces/{workspace_id}/support/id-production")
        assert production.status_code == 200, production.text
        assert (
            production.json()["support_process"]["support_process_id"]
            == first.json()["support_process_id"]
        )
        other_csrf = _login(
            other,
            username="support-scope-other",
            password="Synthetic-Support-Scope-Other-Password-42!",
        )
        hidden = other.post(
            f"/api/v1/workspaces/{workspace_id}/support/processes",
            json=payload,
            headers=other_csrf,
        )
        assert hidden.status_code == 404, hidden.text
        assert hidden.json()["error"]["code"] == "workspace_not_found"
        hidden_readiness = other.get(f"/api/v1/workspaces/{workspace_id}/support/scope-readiness")
        assert hidden_readiness.status_code == 404, hidden_readiness.text
        assert hidden_readiness.json()["error"]["code"] == "workspace_not_found"


def test_browser_to_evidence_project_understanding_is_workspace_scoped(
    postgres_environment: PostgreSQLEnvironment,
    tmp_path: Path,
) -> None:
    work_type_id, catalog_id = _seed_verified_work_type_catalog(postgres_environment)
    settings = _settings(postgres_environment, tmp_path)
    app = create_app(engine=postgres_environment.application_engine, settings=settings)
    owner_identity_id = app.state.container.auth.bootstrap_owner(
        username="understanding-owner",
        password="Synthetic-Owner-Password-42!",
        display_name="Synthetic understanding owner",
    )
    with TestClient(app) as client:
        csrf = _login(client)
        workspace_a = client.post(
            "/api/v1/workspaces", json={"display_name": "Understanding A"}, headers=csrf
        ).json()
        workspace_b = client.post(
            "/api/v1/workspaces", json={"display_name": "Understanding B"}, headers=csrf
        ).json()
        empty = client.get(
            f"/api/v1/workspaces/{workspace_b['workspace_id']}/project-understanding"
        )
        assert empty.status_code == 200
        assert empty.json()["reconciliation"] == {}
        upload = client.post(
            f"/api/v1/workspaces/{workspace_a['workspace_id']}/documents",
            files=[
                (
                    "files",
                    (
                        "explanatory-note.docx",
                        _docx(),
                        "application/octet-stream",
                    ),
                ),
                ("files", ("quantities.csv", _vor_csv(), "text/plain")),
            ],
            headers=csrf,
        )
        assert upload.status_code == 202, upload.text
        assert len(upload.json()["accepted_document_ids"]) == 2

        worker = DocumentWorker(
            SpinePostgresRepository(postgres_environment.document_worker_engine),
            WorkspaceObjectStore(
                settings.object_store_root,
                chunk_bytes=settings.upload_chunk_bytes,
                max_file_bytes=settings.max_file_bytes,
            ),
            worker_identity="synthetic-understanding-worker",
            lease_seconds=5,
            organization_id=UUID(workspace_a["organization_id"]),
            workspace_id=UUID(workspace_a["workspace_id"]),
            qwen_semantic_url=None,  # This fixture exercises native DOCX/CSV extraction.
        )
        outcomes, latest_states = _drain_worker_through_bounded_retries(worker)
        # The exact number of internal materialization jobs is not a product
        # contract. The assertions below verify the required persisted view,
        # evidence navigation and workspace isolation instead.
        assert outcomes
        assert set(latest_states.values()) == {"succeeded"}

        with postgres_environment.document_worker_engine.begin() as connection:
            connection.execute(
                sa.select(
                    sa.func.set_config(
                        "asd.organization_id", str(workspace_a["organization_id"]), True
                    ),
                    sa.func.set_config("asd.workspace_id", workspace_a["workspace_id"], True),
                )
            ).one()
            current = (
                connection.execute(
                    sa.text(
                        "SELECT reconciliation_id,version,project_definition_id,"
                        "open_defect_count FROM workspace.project_understanding_reconciliations "
                        "WHERE organization_id=:o "
                        "AND workspace_id=:w ORDER BY recorded_at DESC,reconciliation_id DESC "
                        "LIMIT 1"
                    ),
                    {"o": workspace_a["organization_id"], "w": workspace_a["workspace_id"]},
                )
                .mappings()
                .one()
            )
            assert (
                connection.scalar(
                    sa.text(
                        "SELECT count(*) FROM "
                        "workspace.project_reconciliation_work_package_memberships "
                        "WHERE organization_id=:o AND workspace_id=:w AND reconciliation_id=:r "
                        "AND reconciliation_version=:v"
                    ),
                    {
                        "o": workspace_a["organization_id"],
                        "w": workspace_a["workspace_id"],
                        "r": current["reconciliation_id"],
                        "v": current["version"],
                    },
                )
                == 1
            )
            assert (
                connection.scalar(
                    sa.text(
                        "SELECT count(*) FROM "
                        "workspace.project_reconciliation_defect_memberships "
                        "WHERE organization_id=:o AND workspace_id=:w AND reconciliation_id=:r "
                        "AND reconciliation_version=:v"
                    ),
                    {
                        "o": workspace_a["organization_id"],
                        "w": workspace_a["workspace_id"],
                        "r": current["reconciliation_id"],
                        "v": current["version"],
                    },
                )
                == current["open_defect_count"]
            )
            connection.execute(
                sa.text(
                    "INSERT INTO workspace.construction_work_package_versions "
                    "(organization_id,workspace_id,work_package_id,version,project_definition_id,"
                    "project_definition_version,work_type_key,work_type_version,package,fingerprint,"
                    "created_at) VALUES (:o,:w,:package,1,:project,1,'historical.unbound','1.0.0',"
                    "CAST(:document AS jsonb),:fingerprint,CURRENT_TIMESTAMP)"
                ),
                {
                    "o": workspace_a["organization_id"],
                    "w": workspace_a["workspace_id"],
                    "package": UUID("73000000-0000-4000-8000-000000000001"),
                    "project": current["project_definition_id"],
                    "document": json.dumps({"label": "historical unbound package"}),
                    "fingerprint": "sha256:" + "c" * 64,
                },
            )
            connection.execute(
                sa.text(
                    "INSERT INTO workspace.project_reconciliation_defects "
                    "(organization_id,workspace_id,defect_id,version,defect_kind,"
                    "subject_identity,related_identity,source_locator_ids,parameters,blocking,"
                    "status,defect_digest,extraction_profile_version) VALUES "
                    "(:o,:w,:defect,1,'ambiguous_source_match','historical-unbound',NULL,"
                    "ARRAY[]::uuid[],CAST('{}' AS jsonb),false,'open',:digest,"
                    "'superseded-synthetic-profile@1')"
                ),
                {
                    "o": workspace_a["organization_id"],
                    "w": workspace_a["workspace_id"],
                    "defect": UUID("74000000-0000-4000-8000-000000000001"),
                    "digest": "sha256:" + "d" * 64,
                },
            )

        expired_job_id = uuid7()
        with postgres_environment.document_worker_engine.begin() as connection:
            connection.execute(
                sa.select(
                    sa.func.set_config(
                        "asd.organization_id", str(workspace_a["organization_id"]), True
                    ),
                    sa.func.set_config("asd.workspace_id", workspace_a["workspace_id"], True),
                )
            ).one()
            connection.execute(
                sa.text(
                    "INSERT INTO workspace.durable_jobs (organization_id,workspace_id,job_id,"
                    "subject_document_id,job_kind,input_manifest,input_digest,idempotency_key,state,"
                    "priority,created_at,eligible_at,started_at,heartbeat_at,attempt_count,max_attempts,"
                    "retry_policy_version,lease_owner,lease_generation,lease_expires_at,"
                    "cancellation_state,provenance,correlation_id,created_by_identity_id) SELECT "
                    "organization_id,workspace_id,:job,subject_document_id,job_kind,input_manifest,"
                    "input_digest,:idempotency,'running',priority,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP,"
                    "CURRENT_TIMESTAMP,CURRENT_TIMESTAMP-interval '2 minutes',1,1,"
                    "retry_policy_version,'synthetic-crashed-worker',1,"
                    "CURRENT_TIMESTAMP-interval '1 minute','none',provenance,:correlation,"
                    "created_by_identity_id FROM workspace.durable_jobs WHERE organization_id=:o "
                    "AND workspace_id=:w ORDER BY created_at,job_id LIMIT 1"
                ),
                {
                    "job": expired_job_id,
                    "idempotency": f"synthetic-expired:{expired_job_id}",
                    "correlation": uuid7(),
                    "o": workspace_a["organization_id"],
                    "w": workspace_a["workspace_id"],
                },
            )
        repository = SpinePostgresRepository(postgres_environment.document_worker_engine)
        assert (
            repository.reconcile_expired_exhausted_jobs(
                organization_id=UUID(str(workspace_a["organization_id"])),
                workspace_id=UUID(str(workspace_a["workspace_id"])),
            )
            == 1
        )
        with postgres_environment.document_worker_engine.begin() as connection:
            connection.execute(
                sa.select(
                    sa.func.set_config(
                        "asd.organization_id", str(workspace_a["organization_id"]), True
                    ),
                    sa.func.set_config("asd.workspace_id", workspace_a["workspace_id"], True),
                )
            ).one()
            exhausted = connection.execute(
                sa.text(
                    "SELECT state,typed_failure_code,result_receipt_id FROM workspace.durable_jobs "
                    "WHERE organization_id=:o AND workspace_id=:w AND job_id=:job"
                ),
                {
                    "o": workspace_a["organization_id"],
                    "w": workspace_a["workspace_id"],
                    "job": expired_job_id,
                },
            ).one()
            assert exhausted.state == "reconciliation_required"
            assert exhausted.typed_failure_code == "worker_lease_expired_after_attempt_exhaustion"
            assert exhausted.result_receipt_id is not None

        response = client.get(
            f"/api/v1/workspaces/{workspace_a['workspace_id']}/project-understanding"
        )
        assert response.status_code == 200, response.text
        view = response.json()
        assert view["reconciliation"]["terminal_status"] == "partial"
        assert len(view["defects"]) == view["reconciliation"]["open_defect_count"]
        assert all(item["subject_identity"] != "historical-unbound" for item in view["defects"])
        paged_gaps = client.get(
            f"/api/v1/workspaces/{workspace_a['workspace_id']}/project-understanding",
            params={"section": "gaps", "page_offset": 0, "page_limit": 1},
        )
        assert paged_gaps.status_code == 200, paged_gaps.text
        paged_gaps_value = paged_gaps.json()
        assert len(paged_gaps_value["defects"]) == 1
        assert paged_gaps_value["application_page"] == {
            "collection": "defects",
            "offset": 0,
            "limit": 1,
            "returned": 1,
            "total": len(view["defects"]),
            "has_previous": False,
            "has_more": len(view["defects"]) > 1,
        }
        assert view["project_definition"]["definition"]["fields"]["object_name"]["raw_value"] == (
            "Производственный корпус"
        )
        assert view["project_definition"]["definition"]["fields"]["purpose"]["raw_value"] == (
            "Выпуск строительных материалов"
        )
        assert len(view["work_packages"]) == 1
        assert view["facility_work_projection"]["candidate_groups"] == []
        assert view["structure_identity_components"] == []
        assert view["structure_identity_dossiers"] == []
        assert view["facility_work_projection"]["coverage"] == {
            "total_work_package_count": 1,
            "exact_identity_package_count": 0,
            "explicit_label_identity_package_count": 0,
            "ambiguous_identity_package_count": 0,
            "unassociated_package_count": 1,
            "consolidated_candidate_group_count": 0,
            "complete": False,
            "candidate_authority": "candidate_only",
            "association_rule": ("exact_shared_source_locator_or_explicit_unique_identity_label"),
        }
        package = view["work_packages"][0]["package"]
        assert package["work_type"]["raw"] == "Устройство монолитной плиты"
        assert package["work_type"]["mapping_status"] == "resolved"
        assert package["work_type"]["canonical_work_type_id"] == str(work_type_id)
        assert package["work_type"]["canonical_work_type_key"] == "concrete.slab.install"
        assert package["work_type"]["catalog_bindings"] == [
            {
                "catalog_id": str(catalog_id),
                "catalog_version": 1,
                "catalog_fingerprint": "sha256:" + "a" * 64,
            }
        ]
        assert package["quantities"][0]["raw_value"] == "+12,350"
        assert package["quantities"][0]["raw_unit"] == "м³"
        assert package["materials"][0]["raw_name"] == "Бетон В25"
        assert package["uncertainties"] == []
        consultant = ProfessionalAssistantKnowledgeQuery(postgres_environment.application_engine)
        work_context = consultant.execute(
            "consultant.get_work_packages",
            {"mode": "Tender", "query": "монолитная плита", "limit": 20},
            GatewayContext(
                owner_identity_id,
                "consultant.get_work_packages.invoke",
                "integration-test",
                uuid7(),
                UUID(str(workspace_a["organization_id"])),
                UUID(str(workspace_a["workspace_id"])),
            ),
        )
        assert work_context.result["value"]["selection_coverage"] == {
            "query": "монолитная плита",
            "selection": "lexical_relevance",
            "total_observation_count": 1,
            "matched_observation_count": 1,
            "returned_observation_count": 1,
            "exhaustive_for_query": True,
            "authority": "candidate_observations_not_confirmed_work_packages",
        }
        assert (
            work_context.result["value"]["work_packages"][0]["package"]["work_type"]["raw"]
            == "Устройство монолитной плиты"
        )
        assert len(work_context.evidence_pack.evidence) == 1
        assert "WORK_TYPE_CATALOG_UNAVAILABLE" not in view["matrix"]["matrix"]["rows"][0]["gaps"]
        assert view["matrix"]["matrix"]["complete"] is False
        gap_codes = {item["code"] for item in view["normative_profile"]["gaps"]}
        denominator = view["normative_profile"]["corpus_denominator"]
        assert denominator["spds_members"] >= 0
        if denominator["spds_members"]:
            assert denominator["manifest_fingerprint"].startswith("sha256:")
        else:
            assert denominator["gap"] == "SPDS_CORPUS_MANIFEST_UNAVAILABLE"
        assert "VERIFIED_PD_RD_NTD_UNAVAILABLE" in gap_codes
        assert "ACTIVE_PD_RD_RULE_VERSION_UNAVAILABLE" in gap_codes
        assert view["authority_layers"]["normative_authority"] == "verified_subset_only"
        assert view["normative_profile"]["completeness_status"] == "blocked"
        support_view = client.get(
            f"/api/v1/workspaces/{workspace_a['workspace_id']}/support/id-production"
        )
        assert support_view.status_code == 200, support_view.text
        assert support_view.json()["support_process"] is None
        assert "SUPPORT_PROCESS_NOT_CONFIGURED" in support_view.json()["gaps"]
        unsafe_package = client.post(
            f"/api/v1/workspaces/{workspace_a['workspace_id']}/support/id-packages",
            json={"work_package_id": view["work_packages"][0]["work_package_id"]},
            headers=csrf,
        )
        assert unsafe_package.status_code == 409, unsafe_package.text
        assert unsafe_package.json()["error"]["code"] == "support_process_not_configured"
        tender_inputs = {
            item["category"]: item for item in view["intake_summary"]["tender_input_assessment"]
        }
        assert tender_inputs["design_or_working_documentation"]["state"] == "available"
        assert tender_inputs["quantity_or_estimate"]["state"] == "available"
        assert tender_inputs["draft_contract"]["state"] == "not_detected_in_classified_sources"
        assert "Contract changes" in tender_inputs["draft_contract"]["practical_limitation"]
        assert view["page_roles"]
        assert len(view["candidates"]["project_fields"]) == 3
        project_candidate_ids = [
            UUID(str(item["candidate_id"])) for item in view["candidates"]["project_fields"]
        ]
        with postgres_environment.owner_engine.connect() as connection:
            bridged = connection.execute(
                sa.text(
                    "SELECT count(DISTINCT version.candidate_id) candidate_count,"
                    "count(DISTINCT evidence.candidate_id) evidence_count,"
                    "count(DISTINCT validation.candidate_id) validation_count FROM "
                    "workspace.candidate_versions version LEFT JOIN "
                    "workspace.candidate_field_evidence evidence ON "
                    "evidence.organization_id=version.organization_id AND "
                    "evidence.workspace_id=version.workspace_id AND "
                    "evidence.candidate_id=version.candidate_id AND "
                    "evidence.candidate_version=version.candidate_version LEFT JOIN "
                    "workspace.vlm_validation_runs validation ON "
                    "validation.organization_id=version.organization_id AND "
                    "validation.workspace_id=version.workspace_id AND "
                    "validation.candidate_id=version.candidate_id AND "
                    "validation.candidate_version=version.candidate_version WHERE "
                    "version.organization_id=:o AND version.workspace_id=:w AND "
                    "version.candidate_id=ANY(:candidates)"
                ),
                {
                    "o": workspace_a["organization_id"],
                    "w": workspace_a["workspace_id"],
                    "candidates": project_candidate_ids,
                },
            ).one()
        assert tuple(bridged) == (3, 3, 3)
        assert len(view["candidates"]["quantities"]) == 1
        tender_schedule = client.get(
            f"/api/v1/workspaces/{workspace_a['workspace_id']}/project-understanding/"
            "tender-findings.csv"
        )
        assert tender_schedule.status_code == 200, tender_schedule.text
        assert tender_schedule.headers["content-type"] == "text/csv; charset=utf-8"
        assert tender_schedule.headers["content-disposition"].startswith("attachment;")
        assert "source_references" in tender_schedule.content.decode("utf-8-sig")
        tender_scope_schedule = client.get(
            f"/api/v1/workspaces/{workspace_a['workspace_id']}/project-understanding/"
            "tender-scope-schedule.csv"
        )
        assert tender_scope_schedule.status_code == 200, tender_scope_schedule.text
        assert tender_scope_schedule.headers["content-type"] == "text/csv; charset=utf-8"
        scope_csv = tender_scope_schedule.content.decode("utf-8-sig")
        assert "work_package_id" in scope_csv
        assert "Устройство монолитной плиты" in scope_csv
        assert "candidate" in scope_csv
        tender_coverage = client.get(
            f"/api/v1/workspaces/{workspace_a['workspace_id']}/project-understanding/"
            "tender-document-coverage.csv"
        )
        assert tender_coverage.status_code == 200, tender_coverage.text
        assert tender_coverage.headers["content-type"] == "text/csv; charset=utf-8"
        coverage_csv = tender_coverage.content.decode("utf-8-sig")
        assert "native_extraction_status" in coverage_csv
        assert "semantic_coverage_state" in coverage_csv
        identity_schedule = client.get(
            f"/api/v1/workspaces/{workspace_a['workspace_id']}/project-understanding/"
            "tender-structure-identity-candidates.csv"
        )
        assert identity_schedule.status_code == 200, identity_schedule.text
        assert identity_schedule.headers["content-type"] == "text/csv; charset=utf-8"
        identity_csv = identity_schedule.content.decode("utf-8-sig")
        assert "automatic_merge" in identity_csv
        assert "member_raw_name" in identity_csv
        facility_scope_schedule = client.get(
            f"/api/v1/workspaces/{workspace_a['workspace_id']}/project-understanding/"
            "tender-facility-work-observations.csv"
        )
        assert facility_scope_schedule.status_code == 200, facility_scope_schedule.text
        assert facility_scope_schedule.headers["content-type"] == "text/csv; charset=utf-8"
        assert "association_state" in facility_scope_schedule.content.decode("utf-8-sig")
        tender_archive = client.get(
            f"/api/v1/workspaces/{workspace_a['workspace_id']}/project-understanding/"
            "tender-analysis.zip"
        )
        assert tender_archive.status_code == 200, tender_archive.text
        assert tender_archive.headers["content-type"] == "application/zip"
        with zipfile.ZipFile(io.BytesIO(tender_archive.content)) as exported:
            assert exported.namelist() == [
                "01_tender_findings_report.docx",
                "02_tender_findings_schedule.csv",
                "03_tender_work_resource_schedule.csv",
                "04_structure_identity_candidates.csv",
                "05_facility_work_observation_candidates.csv",
                "06_facility_work_candidate_groups.csv",
                "07_document_processing_coverage.csv",
                "08_delivery_manifest.json",
                "99_analysis_status.txt",
            ]
            assert "candidate_status" in exported.read(
                "06_facility_work_candidate_groups.csv"
            ).decode("utf-8-sig")
        tender_report = client.get(
            f"/api/v1/workspaces/{workspace_a['workspace_id']}/project-understanding/"
            "tender-findings.docx"
        )
        assert tender_report.status_code == 200, tender_report.text
        assert (
            tender_report.headers["content-type"]
            == "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        )
        with zipfile.ZipFile(io.BytesIO(tender_report.content)) as report:
            assert "word/document.xml" in report.namelist()
        object_locator = view["project_definition"]["definition"]["fields"]["object_name"][
            "source_locator_id"
        ]
        assert object_locator in view["evidence_index"]
        exact = client.get(
            f"/api/v1/workspaces/{workspace_a['workspace_id']}/evidence/locators/{object_locator}"
        )
        assert exact.status_code == 200, exact.text
        assert exact.json()["locator"]["source_locator_id"] == object_locator
        assert exact.json()["locator"]["region"] != [0.0, 0.0, 1.0, 1.0]
        assert (
            client.get(
                f"/api/v1/workspaces/{workspace_b['workspace_id']}/evidence/locators/"
                f"{object_locator}"
            ).status_code
            == 404
        )
        isolated = client.get(
            f"/api/v1/workspaces/{workspace_b['workspace_id']}/project-understanding"
        )
        assert isolated.status_code == 200
        assert isolated.json()["candidates"]["project_fields"] == []

        quantity = view["candidates"]["quantities"][0]
        review = client.post(
            f"/api/v1/workspaces/{workspace_a['workspace_id']}/project-understanding/reviews",
            json={
                "candidate_kind": "quantity",
                "candidate_id": quantity["candidate_id"],
                "candidate_version": quantity["version"],
                "action": "corrected",
                "resolved_value": "13.000",
                "reason": "Исправлено по контрольному фрагменту ведомости",
            },
            headers=csrf,
        )
        assert review.status_code == 201, review.text
        first_run = client.post(
            f"/api/v1/workspaces/{workspace_a['workspace_id']}/project-understanding/runs",
            headers=csrf,
        )
        second_run = client.post(
            f"/api/v1/workspaces/{workspace_a['workspace_id']}/project-understanding/runs",
            headers=csrf,
        )
        assert first_run.status_code == second_run.status_code == 202
        assert first_run.json()["job_id"] == second_run.json()["job_id"]
        project_run_id = UUID(first_run.json()["job_id"])
        post_review_outcomes = []
        while outcome := worker.run_once():
            post_review_outcomes.append(outcome)
            if outcome.job_id == str(project_run_id):
                break
        assert post_review_outcomes
        assert post_review_outcomes[-1].job_id == str(project_run_id)
        assert post_review_outcomes[-1].state.value == "succeeded"
        revised = client.get(
            f"/api/v1/workspaces/{workspace_a['workspace_id']}/project-understanding"
        ).json()
        assert revised["review_decisions"][0]["action"] == "corrected"
        assert revised["work_packages"][0]["package"]["quantities"][0]["raw_value"] == "13.000"


def test_zip_intake_retains_container_and_registers_members(
    postgres_environment: PostgreSQLEnvironment,
    tmp_path: Path,
) -> None:
    settings = _settings(postgres_environment, tmp_path)
    app = create_app(engine=postgres_environment.application_engine, settings=settings)
    app.state.container.auth.bootstrap_owner(
        username="archive-owner",
        password="Synthetic-Owner-Password-42!",
        display_name="Synthetic archive owner",
    )
    archive_bytes = io.BytesIO()
    with zipfile.ZipFile(archive_bytes, "w") as archive:
        archive.writestr("ПЗ/описание.docx", _docx())
        archive.writestr("ВОР/объёмы.csv", _vor_csv())
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/session/login",
            json={"username": "archive-owner", "password": "Synthetic-Owner-Password-42!"},
        )
        assert response.status_code == 200
        csrf = {"X-CSRF-Token": str(client.cookies.get("asd_csrf"))}
        workspace = client.post(
            "/api/v1/workspaces", json={"display_name": "Archive intake"}, headers=csrf
        ).json()
        uploaded = client.post(
            f"/api/v1/workspaces/{workspace['workspace_id']}/documents",
            files=[("files", ("исходные.zip", archive_bytes.getvalue(), "application/zip"))],
            headers=csrf,
        )
        assert uploaded.status_code == 202, uploaded.text
        assert len(uploaded.json()["accepted_document_ids"]) == 3
        documents = client.get(
            f"/api/v1/workspaces/{workspace['workspace_id']}/documents?limit=20"
        ).json()["items"]
        assert {item["media_type"] for item in documents} == {
            "application/zip",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "text/csv",
        }
        assert any(item["relative_path"] == "исходные/ПЗ/описание.docx" for item in documents)
        organization_id = workspace["organization_id"]
        with postgres_environment.document_worker_engine.begin() as connection:
            connection.execute(
                sa.select(
                    sa.func.set_config("asd.organization_id", str(organization_id), True),
                    sa.func.set_config("asd.workspace_id", workspace["workspace_id"], True),
                )
            ).one()
            assert (
                connection.scalar(
                    sa.text(
                        "SELECT count(*) FROM workspace.intake_archive_members WHERE "
                        "organization_id=:o AND workspace_id=:w"
                    ),
                    {"o": organization_id, "w": workspace["workspace_id"]},
                )
                == 2
            )
        worker = DocumentWorker(
            SpinePostgresRepository(postgres_environment.document_worker_engine),
            WorkspaceObjectStore(
                settings.object_store_root,
                chunk_bytes=settings.upload_chunk_bytes,
                max_file_bytes=settings.max_file_bytes,
            ),
            worker_identity="synthetic-archive-worker",
            lease_seconds=5,
            organization_id=UUID(workspace["organization_id"]),
            workspace_id=UUID(workspace["workspace_id"]),
            qwen_semantic_url=None,  # Archive members are native DOCX/CSV fixtures.
        )
        outcomes, latest_states = _drain_worker_through_bounded_retries(worker)
        assert outcomes
        assert set(latest_states.values()) == {"succeeded"}


def test_qualified_synthetic_corpus_reaches_reviewable_project_model(
    postgres_environment: PostgreSQLEnvironment,
    tmp_path: Path,
) -> None:
    corpus_root = tmp_path / "qualified-corpus"
    manifest = _build_synthetic_corpus(corpus_root)
    settings = _settings(postgres_environment, tmp_path)
    app = create_app(engine=postgres_environment.application_engine, settings=settings)
    app.state.container.auth.bootstrap_owner(
        username="understanding-owner",
        password="Synthetic-Owner-Password-42!",
        display_name="Synthetic understanding owner",
    )
    files = [
        path
        for path in sorted(corpus_root.rglob("*"))
        if path.is_file() and path.name != "corpus-manifest.json"
    ]
    relative_paths = [path.relative_to(corpus_root).as_posix() for path in files]
    with TestClient(app) as client:
        csrf = _login(client)
        workspace = client.post(
            "/api/v1/workspaces",
            json={"display_name": "Квалификационный обезличенный объект"},
            headers=csrf,
        ).json()
        workspace_id = workspace["workspace_id"]
        workspace_b = client.post(
            "/api/v1/workspaces",
            json={"display_name": "Изолированный контрольный объект"},
            headers=csrf,
        ).json()
        uploaded = client.post(
            f"/api/v1/workspaces/{workspace_id}/documents",
            files=[
                ("files", (path.name, path.read_bytes(), "application/octet-stream"))
                for path in files
            ],
            data={"relative_paths": json.dumps(relative_paths, ensure_ascii=False)},
            headers=csrf,
        )
        assert uploaded.status_code == 202, uploaded.text
        batch = uploaded.json()
        assert batch["rejected_count"] == 1
        assert len(batch["accepted_document_ids"]) == 14
        controlled_job_id = batch["job_ids"][0]
        paused = client.post(
            f"/api/v1/workspaces/{workspace_id}/jobs/{controlled_job_id}/pause",
            headers=csrf,
        )
        assert paused.status_code == 200, paused.text
        assert paused.json()["state"] == "paused"
        resumed = client.post(
            f"/api/v1/workspaces/{workspace_id}/jobs/{controlled_job_id}/resume",
            headers=csrf,
        )
        assert resumed.status_code == 200, resumed.text
        assert resumed.json()["state"] == "queued"

        repeated_path = corpus_root / "01_Проект" / "Раздел_ПД.pdf"
        repeated = client.post(
            f"/api/v1/workspaces/{workspace_id}/documents",
            files=[
                (
                    "files",
                    (repeated_path.name, repeated_path.read_bytes(), "application/pdf"),
                )
            ],
            data={"relative_paths": json.dumps(["01_Проект/Раздел_ПД.pdf"], ensure_ascii=False)},
            headers=csrf,
        )
        assert repeated.status_code == 202, repeated.text
        assert len(repeated.json()["duplicate_document_ids"]) == 1
        assert repeated.json()["job_ids"] == []

        worker = DocumentWorker(
            SpinePostgresRepository(postgres_environment.document_worker_engine),
            WorkspaceObjectStore(
                settings.object_store_root,
                chunk_bytes=settings.upload_chunk_bytes,
                max_file_bytes=settings.max_file_bytes,
            ),
            worker_identity="qualified-corpus-worker",
            lease_seconds=5,
            organization_id=UUID(workspace["organization_id"]),
            workspace_id=UUID(workspace_id),
            qwen_semantic_url=None,
        )
        outcomes = []
        for _ in range(1000):
            outcome = worker.run_once()
            if outcome is None:
                break
            outcomes.append(outcome)
        else:
            pytest.fail("qualified corpus worker did not reach a terminal queue state")
        states = {outcome.state.value for outcome in outcomes}
        assert "succeeded" in states
        assert "failed" in states
        failed_job_id = next(
            outcome.job_id for outcome in outcomes if outcome.state.value == "failed"
        )
        retried = client.post(
            f"/api/v1/workspaces/{workspace_id}/jobs/{failed_job_id}/retry",
            headers=csrf,
        )
        assert retried.status_code == 202, retried.text
        assert retried.json()["state"] == "queued"
        assert retried.json()["job_id"] != failed_job_id
        assert worker.run_once() is not None

        documents = client.get(
            f"/api/v1/workspaces/{workspace_id}/documents?limit=200&sort=recorded_asc"
        ).json()["items"]
        assert len(documents) == 14
        assert sum(item["admission_status"] == "quarantined" for item in documents) == 1
        assert sum(item["media_type"] == "application/zip" for item in documents) == 1
        assert sum("Дополнительный_комплект/" in item["relative_path"] for item in documents) == 2

        view_response = client.get(f"/api/v1/workspaces/{workspace_id}/project-understanding")
        assert view_response.status_code == 200, view_response.text
        view = view_response.json()
        denominator = manifest["control_denominator"]
        with postgres_environment.owner_engine.connect() as diagnostic_connection:
            diagnostics = [
                dict(row)
                for row in diagnostic_connection.execute(
                    sa.text(
                        "SELECT j.job_kind,j.typed_failure_code,r.result_manifest FROM "
                        "workspace.durable_jobs j LEFT JOIN workspace.job_terminal_receipts r ON "
                        "r.organization_id=j.organization_id AND r.workspace_id=j.workspace_id AND "
                        "r.job_id=j.job_id WHERE j.workspace_id=:workspace "
                        "AND j.state<> 'succeeded'"
                    ),
                    {"workspace": workspace_id},
                ).mappings()
            ]
        assert view["project_definition"]["definition"]["fields"], [diagnostics]
        assert len(view["work_packages"]) >= int(denominator["work_types"])
        assert len(view["candidates"]["quantities"]) >= int(denominator["quantities"])
        assert len(view["candidates"]["materials"]) >= int(denominator["materials"])
        assert view["matrix"]["matrix"]["rows"]
        assert view["defects"]
        projection_repository = IndustrialUnderstandingRepository(
            postgres_environment.document_worker_engine
        )
        first_projection = projection_repository.rebuild_project_understanding_projection(
            organization_id=UUID(workspace["organization_id"]),
            workspace_id=UUID(workspace_id),
        )
        with postgres_environment.document_worker_engine.begin() as connection:
            connection.execute(
                sa.select(
                    sa.func.set_config(
                        "asd.organization_id", str(workspace["organization_id"]), True
                    ),
                    sa.func.set_config("asd.workspace_id", workspace_id, True),
                )
            ).one()
            connection.execute(
                sa.text(
                    "DELETE FROM projection.project_understanding_entries "
                    "WHERE workspace_id=:workspace"
                ),
                {"workspace": workspace_id},
            )
        rebuilt_projection = projection_repository.rebuild_project_understanding_projection(
            organization_id=UUID(workspace["organization_id"]),
            workspace_id=UUID(workspace_id),
        )
        assert rebuilt_projection == first_projection

        quantity = view["candidates"]["quantities"][0]
        reviewed = client.post(
            f"/api/v1/workspaces/{workspace_id}/project-understanding/reviews",
            json={
                "candidate_kind": "quantity",
                "candidate_id": quantity["candidate_id"],
                "candidate_version": quantity["version"],
                "action": "confirmed",
                "reason": "Сверено с контрольным фрагментом ведомости",
            },
            headers=csrf,
        )
        assert reviewed.status_code == 201, reviewed.text
        exact = client.get(
            f"/api/v1/workspaces/{workspace_id}/evidence/locators/{quantity['source_locator_id']}"
        )
        assert exact.status_code == 200, exact.text
        assert exact.json()["locator"]["source_locator_id"] == quantity["source_locator_id"]

        pilot_results: dict[str, dict[str, object]] = {}
        for mode in ("Tender", "Support", "Audit", "Restoration"):
            formed = client.post(
                f"/api/v1/workspaces/{workspace_id}/modes/{mode}/result",
                headers=csrf,
            )
            assert formed.status_code == 201, formed.text
            pilot_results[mode] = formed.json()
            assert pilot_results[mode]["source_manifest"]
            assert pilot_results[mode]["items"]
            assert (
                pilot_results[mode]["normative_notice"]
                == "Актуальность редакций нормативных документов не проверена"
            )

        tender_scope_schedule = pilot_results["Tender"]["tender_scope_schedule"]
        assert isinstance(tender_scope_schedule, list)
        assert len(tender_scope_schedule) == len(view["work_packages"])
        assert all(item["candidate_status"] == "candidate" for item in tender_scope_schedule)
        assert all(item["source_locator_ids"] for item in tender_scope_schedule)
        assert all(item["source_references"] for item in tender_scope_schedule), (
            "Every Tender scope observation must retain a readable evidence pointer"
        )

        audit_items = pilot_results["Audit"]["items"]
        assert isinstance(audit_items, list)
        first_audit_item = audit_items[0]
        assert isinstance(first_audit_item, dict)
        audit_review = client.post(
            f"/api/v1/workspaces/{workspace_id}/modes/Audit/result/items/"
            f"{first_audit_item['item_id']}/reviews",
            json={
                "action": "status_changed",
                "resolved_fields": {"status": "requires_clarification"},
                "comment": "Ответственный назначается после проверки исходного фрагмента",
            },
            headers=csrf,
        )
        assert audit_review.status_code == 201, audit_review.text
        assert audit_review.json()["reviewed_item_count"] == 1

        audit_projection_export = client.get(
            f"/api/v1/workspaces/{workspace_id}/audit/reports/latest.csv"
        )
        assert audit_projection_export.status_code == 200, audit_projection_export.text
        assert audit_projection_export.headers["content-type"] == "text/csv; charset=utf-8"
        audit_projection_csv = audit_projection_export.content.decode("utf-8-sig")
        assert "record_kind" in audit_projection_csv
        assert "CANONICAL_AUDIT_REPORT_NOT_PUBLISHED" in audit_projection_csv

        for kind, output_format in (
            ("disagreement_protocol", "docx"),
            ("contract_changes", "pdf"),
        ):
            blocked_contract_export = client.post(
                f"/api/v1/workspaces/{workspace_id}/modes/Tender/exports",
                json={"export_kind": kind, "output_format": output_format},
                headers=csrf,
            )
            assert blocked_contract_export.status_code == 409, blocked_contract_export.text
            assert (
                blocked_contract_export.json()["error"]["code"]
                == "pilot_contract_analysis_required"
            )

        export_cases = (
            ("Support", "requirement_matrix", "pdf"),
            ("Support", "id_package", "zip"),
            ("Support", "register", "docx"),
            ("Audit", "audit_report", "docx"),
            ("Audit", "audit_report", "pdf"),
            ("Restoration", "recovery_plan", "docx"),
            ("Restoration", "recovery_plan", "pdf"),
            ("Restoration", "recovered_drafts", "zip"),
            ("Tender", "workspace_results", "zip"),
        )
        created_exports = []
        for mode, kind, output_format in export_cases:
            created = client.post(
                f"/api/v1/workspaces/{workspace_id}/modes/{mode}/exports",
                json={"export_kind": kind, "output_format": output_format},
                headers=csrf,
            )
            assert created.status_code == 201, created.text
            export = created.json()
            assert export["size_bytes"] > 100
            assert export["content_digest"].startswith("sha256:")
            created_exports.append(export)
        tender_item = pilot_results["Tender"]["items"][0]
        assert isinstance(tender_item, dict)
        accepted_tender_item = client.post(
            f"/api/v1/workspaces/{workspace_id}/modes/Tender/result/items/"
            f"{tender_item['item_id']}/reviews",
            json={
                "action": "accepted",
                "resolved_fields": None,
                "comment": "Вывод принят после повторной проверки источника",
            },
            headers=csrf,
        )
        assert accepted_tender_item.status_code == 201, accepted_tender_item.text
        regenerated_archive = client.post(
            f"/api/v1/workspaces/{workspace_id}/modes/Tender/exports",
            json={"export_kind": "workspace_results", "output_format": "zip"},
            headers=csrf,
        )
        assert regenerated_archive.status_code == 201, regenerated_archive.text
        assert regenerated_archive.json()["export_id"] == created_exports[-1]["export_id"]
        assert regenerated_archive.json()["version"] == created_exports[-1]["version"] + 1
        unchanged_archive = client.post(
            f"/api/v1/workspaces/{workspace_id}/modes/Tender/exports",
            json={"export_kind": "workspace_results", "output_format": "zip"},
            headers=csrf,
        )
        assert unchanged_archive.status_code == 201, unchanged_archive.text
        assert unchanged_archive.json() == regenerated_archive.json()
        refreshed_tender = client.get(f"/api/v1/workspaces/{workspace_id}/modes/Tender/result")
        assert refreshed_tender.status_code == 200, refreshed_tender.text
        latest_exports = refreshed_tender.json()["exports"]
        export_ids = [item["export_id"] for item in latest_exports]
        assert len(export_ids) == len(set(export_ids))
        assert (
            next(
                item
                for item in latest_exports
                if item["export_id"] == created_exports[-1]["export_id"]
            )["version"]
            == regenerated_archive.json()["version"]
        )
        content = client.get(
            f"/api/v1/workspaces/{workspace_id}/pilot-exports/"
            f"{created_exports[-1]['export_id']}/content"
        )
        assert content.status_code == 200
        assert content.headers["accept-ranges"] == "bytes"
        with zipfile.ZipFile(io.BytesIO(content.content)) as archive:
            names = set(archive.namelist())
        assert "manifest.json" in names
        assert "tender/result.docx" in names
        assert "support/result.pdf" in names
        ranged = client.get(
            f"/api/v1/workspaces/{workspace_id}/pilot-exports/"
            f"{created_exports[0]['export_id']}/content",
            headers={"Range": "bytes=0-63"},
        )
        assert ranged.status_code == 206
        assert len(ranged.content) == 64
        assert ranged.headers["content-range"].startswith("bytes 0-63/")
        assert (
            client.get(
                f"/api/v1/workspaces/{workspace_b['workspace_id']}/modes/Tender/result"
            ).status_code
            == 404
        )

        with postgres_environment.document_worker_engine.begin() as connection:
            connection.execute(
                sa.select(
                    sa.func.set_config(
                        "asd.organization_id", str(workspace["organization_id"]), True
                    ),
                    sa.func.set_config("asd.workspace_id", workspace_id, True),
                )
            ).one()
            assert connection.scalar(
                sa.text(
                    "SELECT count(*) FROM workspace.intake_archive_members "
                    "WHERE workspace_id=:workspace"
                ),
                {"workspace": workspace_id},
            ) == int(denominator["expected_intake_outcomes"]["archive_members"])

        receipt_path = os.environ.get("ASD_INTAKE_CORPUS_RECEIPT")
        if receipt_path:
            destination = Path(receipt_path)
            if not destination.is_absolute():
                raise ValueError("ASD_INTAKE_CORPUS_RECEIPT must be outside Git")
            with postgres_environment.owner_engine.connect() as connection:
                job_counts = dict(
                    connection.execute(
                        sa.text(
                            "SELECT state,count(*) FROM workspace.durable_jobs "
                            "WHERE workspace_id=:workspace GROUP BY state"
                        ),
                        {"workspace": workspace_id},
                    ).all()
                )
                page_routes = {
                    f"{kind}:{route}": int(count)
                    for kind, route, count in connection.execute(
                        sa.text(
                            "SELECT primary_kind,ocr_route,count(*) FROM "
                            "workspace.document_page_health_versions WHERE workspace_id=:workspace "
                            "GROUP BY primary_kind,ocr_route"
                        ),
                        {"workspace": workspace_id},
                    ).all()
                }
            receipt = {
                "corpus_version": manifest["corpus_version"],
                "logical_fingerprint": manifest["logical_fingerprint"],
                "selected_files": len(files),
                "accepted_documents": len(batch["accepted_document_ids"]),
                "rejected_uploads": batch["rejected_count"],
                "duplicate_replay": len(repeated.json()["duplicate_document_ids"]),
                "registered_documents": len(documents),
                "quarantined_documents": sum(
                    item["admission_status"] == "quarantined" for item in documents
                ),
                "job_counts": dict(sorted(job_counts.items())),
                "page_routes": dict(sorted(page_routes.items())),
                "project_fields": len(view["candidates"]["project_fields"]),
                "work_types": len(view["candidates"]["work_types"]),
                "quantities": len(view["candidates"]["quantities"]),
                "materials": len(view["candidates"]["materials"]),
                "work_packages": len(view["work_packages"]),
                "matrix_rows": len(view["matrix"]["matrix"]["rows"]),
                "defects": len(view["defects"]),
                "review_decisions": 1,
            }
            destination.write_text(
                json.dumps(receipt, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                encoding="utf-8",
            )

        prepared = client.post(
            f"/api/v1/workspaces/{workspace_id}/lifecycle/reset/prepare",
            json={"confirmation": "PREPARE_WORKSPACE_RESET"},
            headers=csrf,
        )
        assert prepared.status_code == 200, prepared.text
        challenge = prepared.json()
        reset = client.post(
            f"/api/v1/workspaces/{workspace_id}/lifecycle/reset/execute",
            json={
                "challenge_id": challenge["challenge_id"],
                "confirmation_text": challenge["confirmation_text"],
            },
            headers=csrf,
        )
        assert reset.status_code == 200, reset.text
        assert reset.json()["outcome"] == "verified"
        remaining_workspace_ids = {
            item["workspace_id"] for item in client.get("/api/v1/workspaces").json()
        }
        assert workspace_id not in remaining_workspace_ids
        assert workspace_b["workspace_id"] in remaining_workspace_ids
        with postgres_environment.owner_engine.connect() as connection:
            for table in (
                "intake_archive_members",
                "project_candidate_review_decisions",
                "pilot_export_versions",
                "pilot_result_item_decisions",
                "pilot_mode_result_versions",
            ):
                assert (
                    connection.scalar(
                        sa.text(
                            f"SELECT count(*) FROM workspace.{table} WHERE workspace_id=:workspace"
                        ),
                        {"workspace": workspace_id},
                    )
                    == 0
                )


@pytest.mark.skipif(
    not os.environ.get("ASD_LOCAL_QWEN_ACCEPTANCE_URL"),
    reason="ASD_LOCAL_QWEN_ACCEPTANCE_URL enables the sequential local-model acceptance",
)
def test_local_qwen_free_text_support_work_is_persisted_with_exact_evidence(
    postgres_environment: PostgreSQLEnvironment,
    tmp_path: Path,
) -> None:
    """The production-shaped worker must persist useful local-Qwen engineering evidence."""

    _seed_verified_work_type_catalog(postgres_environment)
    settings = _settings(postgres_environment, tmp_path)
    app = create_app(engine=postgres_environment.application_engine, settings=settings)
    app.state.container.auth.bootstrap_owner(
        username="understanding-owner",
        password="Synthetic-Owner-Password-42!",
        display_name="Synthetic understanding owner",
    )
    with TestClient(app) as client:
        csrf = _login(client)
        workspace = client.post(
            "/api/v1/workspaces",
            json={"display_name": "Квалификация Support через локальный Qwen"},
            headers=csrf,
        ).json()
        uploaded = client.post(
            f"/api/v1/workspaces/{workspace['workspace_id']}/documents",
            files=[
                (
                    "files",
                    (
                        "support-source.docx",
                        _support_qwen_qualification_docx(),
                        "application/octet-stream",
                    ),
                )
            ],
            headers=csrf,
        )
        assert uploaded.status_code == 202, uploaded.text
        worker = DocumentWorker(
            SpinePostgresRepository(postgres_environment.document_worker_engine),
            WorkspaceObjectStore(
                settings.object_store_root,
                chunk_bytes=settings.upload_chunk_bytes,
                max_file_bytes=settings.max_file_bytes,
            ),
            worker_identity="local-qwen-support-qualification-worker",
            lease_seconds=900,
            organization_id=UUID(workspace["organization_id"]),
            workspace_id=UUID(workspace["workspace_id"]),
            qwen_semantic_url=str(os.environ["ASD_LOCAL_QWEN_ACCEPTANCE_URL"]),
        )
        outcomes, states = _drain_worker_through_bounded_retries(worker, timeout_seconds=1_800)
        assert outcomes
        assert set(states.values()) == {"succeeded"}, {
            "states": states,
            "outcomes": [
                (outcome.job_id, outcome.state.value, outcome.outcome_code)
                for outcome in outcomes
                if outcome.state.value != "succeeded"
            ],
        }

        view = client.get(f"/api/v1/workspaces/{workspace['workspace_id']}/project-understanding")
        assert view.status_code == 200, view.text
        payload = view.json()
        with postgres_environment.owner_engine.connect() as connection:
            accepted = (
                connection.execute(
                    sa.text(
                        "SELECT source_version_id,batch_digest,source_locator_ids,"
                        "terminal_status,"
                        "output_digest,output_manifest FROM "
                        "workspace.engineering_extraction_batches "
                        "WHERE organization_id=:o AND workspace_id=:w AND "
                        "terminal_status='accepted'"
                    ),
                    {"o": workspace["organization_id"], "w": workspace["workspace_id"]},
                )
                .mappings()
                .all()
            )
            materialization_diagnostics = {
                "jobs": [
                    dict(item)
                    for item in connection.execute(
                        sa.text(
                            "SELECT job_id,job_kind,state,input_digest,provenance,"
                            "result_receipt_id "
                            "FROM workspace.durable_jobs WHERE organization_id=:o AND "
                            "workspace_id=:w ORDER BY created_at,job_id"
                        ),
                        {"o": workspace["organization_id"], "w": workspace["workspace_id"]},
                    )
                    .mappings()
                    .all()
                ],
                "stage_results": [
                    dict(item)
                    for item in connection.execute(
                        sa.text(
                            "SELECT job_id,stage_kind,terminal_status,profile_version,"
                            "source_version_id "
                            "FROM workspace.project_understanding_stage_results WHERE "
                            "organization_id=:o AND workspace_id=:w ORDER BY "
                            "recorded_at,stage_result_id"
                        ),
                        {"o": workspace["organization_id"], "w": workspace["workspace_id"]},
                    )
                    .mappings()
                    .all()
                ],
                "works": [
                    dict(item)
                    for item in connection.execute(
                        sa.text(
                            "SELECT candidate_id,raw_name,normalized_name,source_version_id,"
                            "extraction_profile_version FROM workspace.work_type_candidates "
                            "WHERE organization_id=:o AND workspace_id=:w ORDER BY "
                            "candidate_id,version"
                        ),
                        {"o": workspace["organization_id"], "w": workspace["workspace_id"]},
                    )
                    .mappings()
                    .all()
                ],
                "package_count": int(
                    connection.scalar(
                        sa.text(
                            "SELECT count(*) FROM workspace.construction_work_package_versions "
                            "WHERE organization_id=:o AND workspace_id=:w"
                        ),
                        {"o": workspace["organization_id"], "w": workspace["workspace_id"]},
                    )
                    or 0
                ),
            }
        assert accepted
        assert all(item["source_locator_ids"] for item in accepted)
        assert all(str(item["output_digest"]).startswith("sha256:") for item in accepted)
        supported_work = [
            item
            for item in payload["work_packages"]
            if item["package"]["work_type"].get("canonical_work_type_key")
            == "concrete.slab.install"
        ]
        assert supported_work, {
            "work_packages": payload["work_packages"],
            "accepted_manifests": [item["output_manifest"] for item in accepted],
            "materialization": materialization_diagnostics,
        }
        quantities = payload["candidates"]["quantities"]
        assert any(item["value"] == "18,4" and item["raw_unit"] == "м³" for item in quantities), (
            quantities
        )
        materials = payload["candidates"]["materials"]
        assert any("В25" in item["value"] for item in materials), materials
