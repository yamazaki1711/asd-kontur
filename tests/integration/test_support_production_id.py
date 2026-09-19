# ruff: noqa: E501, RUF001
from __future__ import annotations

import hashlib
import io
import json
import os
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import sqlalchemy as sa
from fastapi.testclient import TestClient

from asd_kontur.application_spine.auth import OwnerAuthService
from asd_kontur.application_spine.config import SessionProfile, SpineSettings
from asd_kontur.application_spine.object_store import WorkspaceObjectStore
from asd_kontur.application_spine.postgres import SpinePostgresRepository
from asd_kontur.application_spine.worker import DocumentWorker
from asd_kontur.construction_harness.models import (
    RequiredIDDocument,
    RequirementAuthority,
    WorkRequirementMatrix,
    WorkRequirementRow,
)
from asd_kontur.construction_harness.postgres import ConstructionHarnessRepository
from asd_kontur.domain import uuid7
from asd_kontur.kernel import (
    ConfirmCandidateCommand,
    FactClass,
    FactValueKind,
    PostgresCommonKernel,
)
from asd_kontur.lifecycle import StorageAdapterDefinition
from asd_kontur.lifecycle.postgres import PostgresWorkspaceStorageAdapter
from asd_kontur.support.production_postgres import (
    SupportProductionError,
    SupportProductionRepository,
)
from asd_kontur.support.template_postgres import OfficialTemplatePublisher
from asd_kontur.support.template_qualification import (
    OfficialPdfFormProfile,
    PdfOverlayBinding,
    load_official_pdf_form_profile,
)
from asd_kontur.web_app import create_app

from .conftest import PostgreSQLEnvironment
from .test_common_domain_kernel import (
    DIGEST,
    _command,
    _seed_candidate,
    _seed_policy_and_grant,
    _seed_rule,
)
from .test_construction_harness import _project
from .test_support_slice import _grant, _start_support
from .test_workspace_lifecycle import Tenant, create_tenant, workspace_context


def test_support_production_package_generation_and_workspace_isolation(
    postgres_environment: PostgreSQLEnvironment, tmp_path: Path
) -> None:
    tenant = create_tenant(postgres_environment)
    _, support_process_id, _ = _start_support(postgres_environment, tenant)
    store_root = tmp_path / "objects"
    archive_root = tmp_path / "archives"
    store_root.mkdir()
    archive_root.mkdir()
    settings = SpineSettings(
        database_url=postgres_environment.application_engine.url.render_as_string(
            hide_password=False
        ),
        lifecycle_database_url=postgres_environment.lifecycle_engine.url.render_as_string(
            hide_password=False
        ),
        worker_database_url=postgres_environment.document_worker_engine.url.render_as_string(
            hide_password=False
        ),
        destruction_database_url=postgres_environment.destruction_engine.url.render_as_string(
            hide_password=False
        ),
        object_store_root=store_root,
        archive_store_root=archive_root,
        session_profile=SessionProfile.DEVELOPMENT_LOOPBACK,
        audit_pepper="synthetic-support-production-audit-pepper",
    )
    owner = OwnerAuthService(postgres_environment.application_engine, settings).bootstrap_owner(
        username="synthetic-product-owner",
        password="Synthetic-Product-Owner-Password-42!",
        display_name="Synthetic product owner",
    )
    rule_set_id, rule_version_id, evaluation_id, trace_id = _seed_rule(postgres_environment, tenant)
    candidate_id, _, _, _ = _seed_candidate(postgres_environment, tenant)
    policy_id, confirmation_grant_id = _seed_policy_and_grant(postgres_environment, tenant)
    command = _command(candidate_id, policy_id, confirmation_grant_id)
    kernel = PostgresCommonKernel(postgres_environment.kernel_engine)
    fact = kernel.confirm_candidate(context=workspace_context(tenant), command=command)
    assert fact.fact_version == 1
    official_aosr_source = os.environ.get("ASD_SUPPORT_OFFICIAL_AOSR_SOURCE")
    if official_aosr_source:
        _seed_confirmed_aosr_fields(
            postgres_environment,
            tenant,
            kernel,
            candidate_id,
            policy_id,
        )

    project = _project(tenant.organization_id, tenant.workspace_id)
    work = project.work_packages[0]
    harness = ConstructionHarnessRepository(
        postgres_environment.harness_engine, workspace_context(tenant)
    )
    harness.register_project(project)
    harness.register_work_package(project=project, work_package=work, created_at=datetime.now(UTC))
    document_ids = {name: uuid7() for name in ("aosr", "scheme", "quality", "attachment")}
    matrix = WorkRequirementMatrix(
        uuid7(),
        1,
        tenant.organization_id,
        tenant.workspace_id,
        project.project_definition_id,
        project.version,
        (
            WorkRequirementRow(
                work.work_package_id,
                (),
                (),
                (
                    RequiredIDDocument(
                        document_ids["aosr"],
                        "support.aosr",
                        1,
                        "development-candidate@1",
                        ("normative:synthetic-edition@1:clause-1",),
                        RequirementAuthority.NORMATIVE_VERIFIED,
                    ),
                    RequiredIDDocument(
                        document_ids["scheme"],
                        "support.executive-scheme",
                        1,
                        None,
                        ("project:geometry-requirement",),
                        RequirementAuthority.CONTRACTUAL,
                    ),
                    RequiredIDDocument(
                        document_ids["quality"],
                        "support.material-quality",
                        1,
                        None,
                        ("normative:synthetic-edition@1:clause-2",),
                        RequirementAuthority.NORMATIVE_VERIFIED,
                    ),
                    RequiredIDDocument(
                        document_ids["attachment"],
                        "support.control-attachment",
                        1,
                        None,
                        ("practice:synthetic-guidance",),
                        RequirementAuthority.METHODOLOGICAL_ADVISORY,
                    ),
                ),
                (),
            ),
        ),
        (),
        rule_set_id,
        datetime.now(UTC),
    )
    harness.register_matrix(matrix)

    template = _template_docx()
    template_digest = "sha256:" + hashlib.sha256(template).hexdigest()
    store = WorkspaceObjectStore(store_root, chunk_bytes=65536, max_file_bytes=16_000_000)
    template_key = f"platform/templates/{template_digest[7:]}.docx"
    assert store.put_derived(object_key=template_key, content=template)[0] == template_digest
    product_ids = _seed_product_chain(
        postgres_environment,
        tenant.organization_id,
        tenant.workspace_id,
        owner,
        work.work_package_id,
        document_ids["aosr"],
        command.fact_id,
        rule_version_id,
        evaluation_id,
        trace_id,
        support_process_id,
        template_key,
        template_digest,
        len(template),
    )

    product = SupportProductionRepository(postgres_environment.application_engine)
    before = product.view(owner_identity_id=owner, workspace_id=tenant.workspace_id)
    assert before["package"] is None
    formed = product.form_package(
        owner_identity_id=owner,
        workspace_id=tenant.workspace_id,
        work_package_id=work.work_package_id,
    )
    assert formed["memberships"][0]["role"] == "register"
    assert formed["memberships"][0]["ordinal"] == 1
    assert len(formed["memberships"]) == 5
    aosr_membership = next(item for item in formed["memberships"] if item["role"] == "support.aosr")
    started = product.start_generation(
        owner_identity_id=owner,
        workspace_id=tenant.workspace_id,
        membership_id=UUID(str(aosr_membership["membership_id"])),
        idempotency_key="synthetic-support-production-generation-1",
        correlation_id=uuid7(),
    )
    replay = product.start_generation(
        owner_identity_id=owner,
        workspace_id=tenant.workspace_id,
        membership_id=UUID(str(aosr_membership["membership_id"])),
        idempotency_key="synthetic-support-production-generation-1",
        correlation_id=uuid7(),
    )
    assert replay["duplicate"] is True
    assert replay["job_id"] == started["job_id"]

    worker_repository = SpinePostgresRepository(postgres_environment.document_worker_engine)
    interrupted = worker_repository.claim_next_job(
        worker_identity="synthetic-interrupted-generation-worker", lease_seconds=5
    )
    assert interrupted is not None and str(interrupted.job_id) == started["job_id"]
    worker_repository.mark_job_running(
        interrupted, worker_identity="synthetic-interrupted-generation-worker"
    )
    with postgres_environment.owner_engine.begin() as connection:
        connection.execute(
            sa.text(
                "UPDATE workspace.durable_jobs SET lease_expires_at=CURRENT_TIMESTAMP-INTERVAL '1 second' "
                "WHERE organization_id=:o AND workspace_id=:w AND job_id=:job"
            ),
            {
                "o": tenant.organization_id,
                "w": tenant.workspace_id,
                "job": interrupted.job_id,
            },
        )
    worker = DocumentWorker(
        worker_repository,
        store,
        worker_identity="synthetic-support-production-worker",
        lease_seconds=30,
    )
    outcome = worker.run_once()
    assert outcome is not None and outcome.state.value == "succeeded"
    after = product.view(owner_identity_id=owner, workspace_id=tenant.workspace_id)
    generated = next(item for item in after["memberships"] if item["role"] == "support.aosr")
    assert generated["generated_candidate_id"] is not None
    assert generated["job_state"] == "succeeded"
    assert after["package"]["version"] == 2
    assert after["registers"][0]["register_manifest"]["documents"][0]["ordinal"] == 2
    assert "TEMPLATE_NOT_PRODUCTION_QUALIFIED" in after["gaps"]
    assert after["readiness"]["status"] == "incomplete"
    assert after["field_resolutions"][0]["state"] == "confirmed"

    app = create_app(engine=postgres_environment.application_engine, settings=settings)
    with TestClient(app) as client:
        login = client.post(
            "/api/v1/session/login",
            json={
                "username": "synthetic-product-owner",
                "password": "Synthetic-Product-Owner-Password-42!",
            },
        )
        assert login.status_code == 200
        api_view = client.get(f"/api/v1/workspaces/{tenant.workspace_id}/support/id-production")
        assert api_view.status_code == 200
        assert api_view.json()["package"]["version"] == 2
        audit_preflight = client.get(
            f"/api/v1/workspaces/{tenant.workspace_id}/audit/expected-actual-preflight"
        )
        assert audit_preflight.status_code == 200, audit_preflight.text
        preflight = audit_preflight.json()
        assert preflight["assessment_kind"] == "expected_vs_package_preflight"
        assert preflight["status"] == "partial"
        assert preflight["package"]["version"] == 2
        assert all(item["preflight_state"] != "satisfied" for item in preflight["items"])
        assert any(item["preflight_state"] == "generated_candidate" for item in preflight["items"])
        preflight_export = client.get(
            f"/api/v1/workspaces/{tenant.workspace_id}/audit/expected-actual-preflight.csv"
        )
        assert preflight_export.status_code == 200, preflight_export.text
        assert preflight_export.headers["content-type"].startswith("text/csv")
        assert "audit_boundary" in preflight_export.content.decode("utf-8-sig")
        package_export = client.get(
            f"/api/v1/workspaces/{tenant.workspace_id}/support/id-packages/export"
        )
        assert package_export.status_code == 200, package_export.text
        assert package_export.headers["content-type"] == "application/zip"
        with zipfile.ZipFile(io.BytesIO(package_export.content)) as exported:
            assert exported.namelist()[0] == "01_register_candidate.docx"
            with zipfile.ZipFile(
                io.BytesIO(exported.read("01_register_candidate.docx"))
            ) as register:
                assert "word/document.xml" in register.namelist()
            assert "99_missing_or_blocked_items.csv" in exported.namelist()
            assert any(name.endswith("_candidate.docx") for name in exported.namelist())
        content = client.get(
            f"/api/v1/workspaces/{tenant.workspace_id}/support/generated-candidates/"
            f"{generated['generated_candidate_id']}/content",
            headers={"Range": "bytes=0-31"},
        )
        assert content.status_code == 206
        assert content.headers["content-range"].startswith("bytes 0-31/")
        assert content.content.startswith(b"PK")

    if official_aosr_source:
        profile = load_official_pdf_form_profile(
            Path("contracts/templates/support-aosr-344pr-2023-pdf-overlay-v1.json")
        )
        qualified_source = Path(official_aosr_source).read_bytes()
        stable_key = "support.aosr.344pr-2023.official-form"
        qualified_template_version = "344pr-2023@1.0.0"
    else:
        qualified_source = _qualified_test_form_pdf()
        source_digest = "sha256:" + hashlib.sha256(qualified_source).hexdigest()
        profile = OfficialPdfFormProfile(
            "support.test-official-form.binding@1.0.0",
            source_digest,
            "source-version:synthetic-qualified-test-fixture@1",
            "normative-edition:synthetic-qualified-test-fixture@1",
            "https://example.test/qualified-test-fixture.pdf",
            (1,),
            ("Qualified test fixture", "Hidden works act"),
            (PdfOverlayBinding("work_type.classification", 1, 72, 680, 450, 40, 9, 11),),
            "support.pdf-overlay-renderer@1.0.0",
            "support.pdf-print-validator@1.0.0",
        )
        stable_key = "support.test-official-form"
        qualified_template_version = "1.0.0"
    font_path = next(
        path
        for path in (
            Path("/System/Library/Fonts/Supplemental/Arial.ttf"),
            Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
        )
        if path.is_file()
    )
    qualified_publication = OfficialTemplatePublisher(
        postgres_environment.owner_engine, store
    ).publish_pdf_overlay(
        stable_key=stable_key,
        template_version=qualified_template_version,
        field_schema_version=qualified_template_version,
        source_bytes=qualified_source,
        font_bytes=font_path.read_bytes(),
        font_media_type="font/ttf",
        profile=profile,
        required_document_type_id=product_ids["doc_type"],
        required_document_type_version="1.0.0",
    )
    _grant(postgres_environment, tenant, "support.document.review", owner)
    finalizer = OwnerAuthService(postgres_environment.application_engine, settings).bootstrap_owner(
        username="synthetic-independent-finalizer",
        password="Synthetic-Independent-Finalizer-Password-42!",
        display_name="Synthetic independent finalizer",
    )
    with postgres_environment.owner_engine.begin() as connection:
        connection.execute(
            sa.text(
                "INSERT INTO application.owner_organization_grants VALUES "
                "(:owner,:organization,ARRAY['workspace.read','support.finalize'],1,CURRENT_TIMESTAMP)"
            ),
            {"owner": finalizer, "organization": tenant.organization_id},
        )
    _grant(postgres_environment, tenant, "support.deliverable.finalize", finalizer)
    current_aosr = next(item for item in after["memberships"] if item["role"] == "support.aosr")
    production_started = product.start_generation(
        owner_identity_id=owner,
        workspace_id=tenant.workspace_id,
        membership_id=UUID(str(current_aosr["membership_id"])),
        idempotency_key="synthetic-support-production-qualified-generation-1",
        correlation_id=uuid7(),
    )
    assert production_started["state"] == "queued"
    production_outcome = worker.run_once()
    assert production_outcome is not None and production_outcome.state.value == "succeeded"
    production_view = product.view(owner_identity_id=owner, workspace_id=tenant.workspace_id)
    qualified_member = next(
        item for item in production_view["memberships"] if item["role"] == "support.aosr"
    )
    qualified_candidate_id = UUID(str(qualified_member["generated_candidate_id"]))
    assert qualified_member["print_validation_result"] == "print_ready"
    assert qualified_member["template_qualification_state"] == "active"
    product.review_candidate(
        owner_identity_id=owner,
        workspace_id=tenant.workspace_id,
        candidate_id=qualified_candidate_id,
        outcome="approved",
    )
    finalized_view = product.finalize_candidate(
        owner_identity_id=finalizer,
        workspace_id=tenant.workspace_id,
        candidate_id=qualified_candidate_id,
    )
    finalized_member = next(
        item for item in finalized_view["memberships"] if item["role"] == "support.aosr"
    )
    assert finalized_view["package"]["version"] == 4
    assert [item["version"] for item in finalized_view["package_history"]] == [1, 2, 3, 4]
    assert [item["id_package_version"] for item in finalized_view["register_history"]] == [
        1,
        2,
        3,
        4,
    ]
    assert finalized_member["state"] == "finalized"
    assert finalized_member["finalized_document_id"] is not None
    finalized_identity = UUID(str(finalized_member["finalized_document_id"]))
    assert finalized_view["readiness"]["generated_candidate_count"] == 0
    assert finalized_view["readiness"]["finalized_count"] == 1
    assert finalized_view["readiness"]["missing_count"] == 2
    backup = product.record_package_backup_manifest(
        owner_identity_id=owner, workspace_id=tenant.workspace_id
    )
    replayed_backup = product.record_package_backup_manifest(
        owner_identity_id=owner, workspace_id=tenant.workspace_id
    )
    assert replayed_backup["fingerprint"] == backup["fingerprint"]
    assert len(backup["packages"]) == 4
    assert len(backup["finalized_documents"]) == 1
    old_register = backup["registers"][1]
    current_register = backup["registers"][-1]
    assert old_register["manifest_fingerprint"] != current_register["manifest_fingerprint"]
    assert old_register["register_manifest"]["documents"][0]["state"] == "generated_candidate"
    assert current_register["register_manifest"]["documents"][0]["state"] == "finalized"

    app = create_app(engine=postgres_environment.application_engine, settings=settings)
    with TestClient(app) as client:
        login = client.post(
            "/api/v1/session/login",
            json={
                "username": "synthetic-independent-finalizer",
                "password": "Synthetic-Independent-Finalizer-Password-42!",
            },
        )
        assert login.status_code == 200
        finalized_content = client.get(
            f"/api/v1/workspaces/{tenant.workspace_id}/support/finalized-documents/"
            f"{finalized_identity}/content",
            headers={"Range": "bytes=0-31"},
        )
        assert finalized_content.status_code == 206, finalized_content.json()
        assert finalized_content.headers["content-type"] == "application/pdf"
        assert finalized_content.content.startswith(b"%PDF")

    another = create_tenant(postgres_environment)
    try:
        product.view(owner_identity_id=owner, workspace_id=another.workspace_id)
    except SupportProductionError as exc:
        assert exc.code == "workspace_not_found"
    else:
        raise AssertionError("cross-organization package access was not denied")

    if os.environ.get("ASD_SUPPORT_PRODUCTION_PRESERVE_WORKSPACE") == "1":
        return

    adapter = PostgresWorkspaceStorageAdapter(
        postgres_environment.destruction_engine,
        tenant.organization_id,
        StorageAdapterDefinition(
            "postgres.workspace",
            "0.1.0",
            "postgres_workspace_relations",
            "authoritative",
            "workspace",
            True,
            True,
            True,
            True,
            True,
            "1.0.0",
        ),
    )
    for item in adapter.inventory(tenant.workspace_id):
        adapter.purge_item(
            workspace_id=tenant.workspace_id,
            item_id=item.item_id,
            operation_id=uuid7(),
        )
    assert (
        store.purge_workspace(
            organization_id=tenant.organization_id, workspace_id=tenant.workspace_id
        )
        >= 2
    )
    with postgres_environment.owner_engine.connect() as connection:
        for table in (
            "id_package_versions",
            "id_package_document_membership_versions",
            "support_register_candidates",
            "support_generation_runs",
            "support_generated_document_candidates",
            "support_finalized_document_versions",
            "support_package_backup_manifests",
        ):
            assert (
                connection.scalar(
                    sa.text(
                        f"SELECT count(*) FROM workspace.{table} WHERE organization_id=:o "
                        "AND workspace_id=:w"
                    ),
                    {"o": tenant.organization_id, "w": tenant.workspace_id},
                )
                == 0
            )
        assert (
            connection.scalar(
                sa.text(
                    "SELECT count(*) FROM platform.template_versions WHERE template_id=:template "
                    "AND version=:version"
                ),
                {
                    "template": qualified_publication.template_id,
                    "version": qualified_template_version,
                },
            )
            == 1
        )
        assert (
            connection.scalar(
                sa.text(
                    "SELECT count(*) FROM workspace.workspaces WHERE organization_id=:o AND workspace_id=:w"
                ),
                {"o": another.organization_id, "w": another.workspace_id},
            )
            == 1
        )


def _seed_product_chain(
    environment: PostgreSQLEnvironment,
    organization_id: UUID,
    workspace_id: UUID,
    owner: str,
    work_id: UUID,
    aosr_requirement_id: UUID,
    fact_id: UUID,
    rule_version_id: UUID,
    evaluation_id: UUID,
    trace_id: UUID,
    support_process_id: UUID,
    template_key: str,
    template_digest: str,
    template_size: int,
) -> dict[str, UUID]:
    ids = {
        name: uuid7()
        for name in (
            "work_type",
            "structure",
            "element",
            "doc_type",
            "template_source",
            "schema",
            "template",
        )
    }
    generation_grant = _grant(
        environment,
        type(
            "TenantScope", (), {"organization_id": organization_id, "workspace_id": workspace_id}
        )(),
        "support.document.generate",
        owner,
    )
    del generation_grant
    with environment.owner_engine.begin() as connection:
        connection.execute(
            sa.text(
                "INSERT INTO application.owner_identities VALUES "
                "(:owner,'synthetic-product-owner','Synthetic Product Owner','not-used','active',1,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP) "
                "ON CONFLICT (owner_identity_id) DO NOTHING"
            ),
            {"owner": owner},
        )
        connection.execute(
            sa.text(
                "INSERT INTO application.owner_organization_grants VALUES "
                "(:owner,:organization,ARRAY['workspace.read','support.generate'],1,CURRENT_TIMESTAMP)"
            ),
            {"owner": owner, "organization": organization_id},
        )
        connection.execute(
            sa.text(
                "INSERT INTO platform.work_types VALUES (:id,'support.synthetic.work','1.0.0','human:synthetic',CURRENT_TIMESTAMP)"
            ),
            {"id": ids["work_type"], "digest": DIGEST},
        )
        connection.execute(
            sa.text(
                "INSERT INTO platform.work_type_versions VALUES (:id,'1.0.0','1.0.0','Synthetic support work','active',:digest,:digest,NULL,NULL)"
            ),
            {"id": ids["work_type"], "digest": DIGEST},
        )
        connection.execute(
            sa.text(
                "INSERT INTO workspace.construction_structure_versions VALUES "
                "(:o,:w,:structure,1,:fact,1,(SELECT rule_set_version_id FROM workspace.rule_evaluations WHERE rule_evaluation_id=:evaluation),:trace,'active',:digest,CURRENT_TIMESTAMP)"
            ),
            {
                "o": organization_id,
                "w": workspace_id,
                "structure": ids["structure"],
                "fact": fact_id,
                "evaluation": evaluation_id,
                "trace": trace_id,
                "digest": DIGEST,
            },
        )
        connection.execute(
            sa.text(
                "INSERT INTO workspace.construction_element_versions VALUES "
                "(:o,:w,:element,1,:structure,1,NULL,'synthetic_element','E-1','zone-1',:fact,1,:digest,CURRENT_TIMESTAMP)"
            ),
            {
                "o": organization_id,
                "w": workspace_id,
                "structure": ids["structure"],
                "element": ids["element"],
                "fact": fact_id,
                "digest": DIGEST,
            },
        )
        connection.execute(
            sa.text(
                "INSERT INTO workspace.work_instance_versions VALUES "
                "(:o,:w,:work,1,:work_type,'1.0.0',:element,1,'planned',:fact,1,(SELECT rule_set_version_id FROM workspace.rule_evaluations WHERE rule_evaluation_id=:evaluation),:trace,:digest,CURRENT_TIMESTAMP)"
            ),
            {
                "o": organization_id,
                "w": workspace_id,
                "structure": ids["structure"],
                "element": ids["element"],
                "work": work_id,
                "work_type": ids["work_type"],
                "fact": fact_id,
                "evaluation": evaluation_id,
                "trace": trace_id,
                "digest": DIGEST,
            },
        )
        connection.execute(
            sa.text(
                "INSERT INTO platform.required_document_types VALUES "
                "(:type,'support.aosr','human:synthetic',CURRENT_TIMESTAMP)"
            ),
            {"type": ids["doc_type"]},
        )
        connection.execute(
            sa.text(
                "INSERT INTO platform.required_document_type_versions VALUES "
                "(:type,'1.0.0','hidden-work acceptance act','DOCX','active',:rule,:digest)"
            ),
            {"type": ids["doc_type"], "rule": rule_version_id, "digest": DIGEST},
        )
        connection.execute(
            sa.text(
                "INSERT INTO workspace.document_requirement_versions VALUES "
                "(:o,:w,:requirement,1,:work,1,:type,'1.0.0','required','open',:evaluation,:trace,:digest,CURRENT_TIMESTAMP)"
            ),
            {
                "type": ids["doc_type"],
                "rule": rule_version_id,
                "digest": DIGEST,
                "o": organization_id,
                "w": workspace_id,
                "requirement": aosr_requirement_id,
                "work": work_id,
                "evaluation": evaluation_id,
                "trace": trace_id,
            },
        )
        connection.execute(
            sa.text(
                "INSERT INTO platform.template_sources VALUES "
                "(:source,'support.aosr.development-candidate','DOCX','official_candidate',:digest,"
                "'legacy:/Users/oleg/mac_asd/library/templates/acts/344pr/3_AOSR.docx','unverified','candidate',CURRENT_TIMESTAMP)"
            ),
            {"source": ids["template_source"], "digest": DIGEST},
        )
        connection.execute(
            sa.text(
                "INSERT INTO platform.field_schema_versions VALUES "
                "(:schema,'1.0.0','support.aosr.fields',:digest,'candidate',CURRENT_TIMESTAMP)"
            ),
            {"schema": ids["schema"], "digest": DIGEST},
        )
        connection.execute(
            sa.text(
                "INSERT INTO platform.template_versions VALUES "
                "(:template,'1.0.0',:source,'DOCX',:schema,'1.0.0','support.aosr.binding@1.0.0',"
                "'support.template-docx-renderer@1.0.0','support.print-validation@1.0.0',"
                "'candidate','development_candidate','unverified',:template_digest,CURRENT_TIMESTAMP)"
            ),
            {
                "source": ids["template_source"],
                "schema": ids["schema"],
                "template": ids["template"],
                "template_digest": template_digest,
            },
        )
        connection.execute(
            sa.text(
                "INSERT INTO platform.template_artifacts VALUES "
                "(:template,'1.0.0',1,:object,'application/vnd.openxmlformats-officedocument.wordprocessingml.document',"
                ":size,:template_digest,'{\"legacy_decision\":\"REUSE_AFTER_HARDENING\"}'::jsonb,'candidate',:digest,CURRENT_TIMESTAMP)"
            ),
            {
                "template": ids["template"],
                "digest": DIGEST,
                "template_digest": template_digest,
                "object": template_key,
                "size": template_size,
            },
        )
        connection.execute(
            sa.text(
                "INSERT INTO platform.template_field_definitions VALUES "
                "(:schema,'1.0.0','work_type.classification','text',true,true,false,'{{work_type.classification}}',1,:digest)"
            ),
            {"schema": ids["schema"], "digest": DIGEST},
        )
        connection.execute(
            sa.text(
                "INSERT INTO platform.required_document_type_templates VALUES "
                "(:type,'1.0.0',:template,'1.0.0','candidate',:digest,CURRENT_TIMESTAMP)"
            ),
            {
                "source": ids["template_source"],
                "schema": ids["schema"],
                "template": ids["template"],
                "type": ids["doc_type"],
                "digest": DIGEST,
                "template_digest": template_digest,
                "object": template_key,
                "size": template_size,
            },
        )
        assert (
            connection.scalar(
                sa.text(
                    "SELECT count(*) FROM workspace.support_processes WHERE support_process_id=:process"
                ),
                {"process": support_process_id},
            )
            == 1
        )
    return ids


def _template_docx() -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as package:
        package.writestr(
            "[Content_Types].xml",
            b'<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"/>',
        )
        package.writestr(
            "word/document.xml",
            b'<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
            b"<w:body><w:p><w:r><w:t>Act: {{work_type.classification}}</w:t></w:r></w:p>"
            b"</w:body></w:document>",
        )
    return buffer.getvalue()


def _seed_confirmed_aosr_fields(
    environment: PostgreSQLEnvironment,
    tenant: Tenant,
    kernel: PostgresCommonKernel,
    candidate_id: UUID,
    policy_id: UUID,
) -> None:
    values = {
        "object_name": "Синтетический объект капитального строительства, участок З-01",
        "developer_identity": "ООО Синтетический технический заказчик, ОГРН 1000000000000",
        "builder_identity": "АО Синтетический подрядчик, ОГРН 2000000000000",
        "designer_identity": "ООО Синтетический проектировщик, ОГРН 3000000000000",
        "act_number": "АОСР-SYN-001",
        "act_date": "27.08.2026",
        "customer_representative": "Иванов Иван Иванович, инженер технического надзора",
        "builder_representative": "Петров Пётр Петрович, главный инженер",
        "construction_control_representative": "Орлов Олег Олегович, строительный контроль",
        "designer_representative": "Сидоров Сидор Сидорович, главный инженер проекта",
        "work_performer_representative": "Кузнецов Кузьма Кузьмич, производитель работ",
        "inspection_participants": "Представители заказчика, подрядчика и строительного контроля",
        "hidden_work_description": "Устройство защитного слоя бетона на участке З-01",
        "project_document_reference": "РД-SYN-001, лист КЖ-12, редакция 2",
        "materials_and_quality_documents": "Бетон B25 W6 F150; паспорт № SYN-42",
        "control_evidence_documents": "Протокол контроля № LAB-SYN-01",
        "work_start_date": "20.08.2026",
        "work_end_date": "25.08.2026",
        "compliance_basis": "РД-SYN-001 и подтверждённые требования",
        "next_works": "Устройство последующих монолитных конструкций",
        "additional_information": "Дополнительные сведения отсутствуют",
        "paper_copy_count": "2",
        "appendices": "Исполнительная схема; паспорт качества; протокол контроля",
        "customer_signatory_name": "Иванов И. И.",
        "builder_signatory_name": "Петров П. П.",
        "construction_control_signatory_name": "Орлов О. О.",
        "designer_signatory_name": "Сидоров С. С.",
        "work_performer_signatory_name": "Кузнецов К. К.",
    }
    validation_run_id = uuid7()
    grant_id = uuid7()
    with environment.owner_engine.begin() as connection:
        source_version_id = connection.scalar(
            sa.text(
                "SELECT source_version_id FROM workspace.candidates WHERE organization_id=:o "
                "AND workspace_id=:w AND candidate_id=:candidate"
            ),
            {
                "o": tenant.organization_id,
                "w": tenant.workspace_id,
                "candidate": candidate_id,
            },
        )
        assert isinstance(source_version_id, UUID)
        for ordinal, (field_key, value) in enumerate(values.items(), start=1):
            field_path = f"/aosr/{field_key}"
            locator_id = uuid7()
            evidence_link_id = uuid7()
            fragment_digest = "sha256:" + hashlib.sha256(value.encode()).hexdigest()
            connection.execute(
                sa.text(
                    "INSERT INTO workspace.source_locators VALUES "
                    "(:o,:w,:locator,:source,'json_pointer',:key,CAST(:value AS jsonb),"
                    ":digest,CURRENT_TIMESTAMP)"
                ),
                {
                    "o": tenant.organization_id,
                    "w": tenant.workspace_id,
                    "locator": locator_id,
                    "source": source_version_id,
                    "key": f"aosr-field:{ordinal}:{field_key}",
                    "value": json.dumps({"path": field_path, "raw_text": value}),
                    "digest": fragment_digest,
                },
            )
            connection.execute(
                sa.text(
                    "INSERT INTO workspace.candidate_fields "
                    "(organization_id,workspace_id,candidate_id,candidate_version,field_path,"
                    "value_type,typed_value,unit,validation_state) VALUES "
                    "(:o,:w,:candidate,1,:path,'text',to_jsonb(CAST(:value AS text)),NULL,'valid')"
                ),
                {
                    "o": tenant.organization_id,
                    "w": tenant.workspace_id,
                    "candidate": candidate_id,
                    "path": field_path,
                    "value": value,
                },
            )
            connection.execute(
                sa.text(
                    "INSERT INTO workspace.evidence_links "
                    "(organization_id,workspace_id,evidence_link_id,subject_type,subject_id,"
                    "subject_version,source_version_id,source_locator_id,evidence_role,"
                    "validity_status,decision_ref) VALUES "
                    "(:o,:w,:evidence,'candidate_field',:candidate,:subject,:source,:locator,"
                    "'material_field','verified',:decision)"
                ),
                {
                    "o": tenant.organization_id,
                    "w": tenant.workspace_id,
                    "evidence": evidence_link_id,
                    "candidate": candidate_id,
                    "subject": f"1:{field_path}",
                    "source": source_version_id,
                    "locator": locator_id,
                    "decision": f"decision:synthetic-aosr-field:{ordinal}",
                },
            )
            connection.execute(
                sa.text(
                    "INSERT INTO workspace.candidate_field_evidence VALUES "
                    "(:o,:w,:candidate,1,:path,:source,:locator,:evidence,'material_field')"
                ),
                {
                    "o": tenant.organization_id,
                    "w": tenant.workspace_id,
                    "candidate": candidate_id,
                    "path": field_path,
                    "source": source_version_id,
                    "locator": locator_id,
                    "evidence": evidence_link_id,
                },
            )
        connection.execute(
            sa.text(
                "INSERT INTO workspace.vlm_validation_runs VALUES "
                "(:o,:w,:validation,:candidate,1,'support.aosr.synthetic-fields@1.0.0',"
                "ARRAY['schema','locator'],ARRAY[]::text[],'passed',:digest,CURRENT_TIMESTAMP)"
            ),
            {
                "o": tenant.organization_id,
                "w": tenant.workspace_id,
                "validation": validation_run_id,
                "candidate": candidate_id,
                "digest": DIGEST,
            },
        )
        connection.execute(
            sa.text(
                "INSERT INTO workspace.confirmation_authority_grants VALUES "
                "(:o,:w,:grant,1,'human:synthetic-confirmer','fact.confirm',"
                "ARRAY['observation'],'qualification:synthetic-aosr','active',CURRENT_TIMESTAMP,"
                "NULL,'authority:synthetic-aosr',:digest)"
            ),
            {
                "o": tenant.organization_id,
                "w": tenant.workspace_id,
                "grant": grant_id,
                "digest": DIGEST,
            },
        )
    for ordinal, field_key in enumerate(values, start=1):
        kernel.confirm_candidate(
            context=workspace_context(tenant),
            command=ConfirmCandidateCommand(
                uuid7(),
                uuid7(),
                uuid7(),
                0,
                candidate_id,
                1,
                f"/aosr/{field_key}",
                field_key,
                FactClass.OBSERVATION,
                FactValueKind.TEXT,
                policy_id,
                "1.0.0",
                "qualified_human",
                "human:synthetic-confirmer",
                grant_id,
                1,
                None,
                None,
                None,
                None,
                f"confirm-synthetic-aosr-{ordinal}-{field_key}",
                uuid7(),
                uuid7(),
                datetime.now(UTC),
            ),
        )


def _qualified_test_form_pdf() -> bytes:
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas

    buffer = io.BytesIO()
    document = canvas.Canvas(buffer, pagesize=A4, invariant=1)
    document.drawString(72, 780, "Qualified test fixture")
    document.drawString(72, 750, "Hidden works act")
    document.line(72, 675, 523, 675)
    document.showPage()
    document.save()
    return buffer.getvalue()
