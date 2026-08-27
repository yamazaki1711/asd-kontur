from __future__ import annotations

import hashlib
import json
import os
from dataclasses import replace
from pathlib import Path
from uuid import UUID

import pytest
import sqlalchemy as sa
from sqlalchemy.exc import DBAPIError

from asd_kontur.domain import uuid7
from asd_kontur.lifecycle import (
    ArchiveEntry,
    LifecycleState,
    PortableArchiveService,
    PostgresLifecycleRepository,
    PostgresWorkspaceStorageAdapter,
    StorageAdapterDefinition,
)
from asd_kontur.persistence import WorkspaceContext, WorkspaceUnitOfWork
from asd_kontur.support import (
    PostgresSupportProcess,
    ProfessionalAuthority,
    StartSupportProcess,
    SupportCommand,
    SupportCommandType,
    SupportError,
    SupportErrorCode,
    SupportScope,
    SupportState,
)

from .conftest import PostgreSQLEnvironment, create_database, drop_database, run_migration
from .test_common_domain_kernel import _seed_rule
from .test_workspace_lifecycle import (
    Tenant,
    create_tenant,
    transition,
    workspace_context,
)

pytestmark = pytest.mark.postgres
DIGEST = "sha256:" + "a" * 64


def _support_context(tenant: Tenant) -> WorkspaceContext:
    return replace(
        workspace_context(tenant, service=True),
        service_identity_id="service:synthetic-support",
    )


def _create_support_mode(environment: PostgreSQLEnvironment, tenant: Tenant) -> UUID:
    mode_id = uuid7()
    with WorkspaceUnitOfWork(environment.application_engine, workspace_context(tenant)) as unit:
        assert unit.workspaces is not None
        unit.workspaces.create_mode_execution(
            mode_execution_id=mode_id,
            mode="Support",
            purpose="purpose.synthetic.support",
            input_manifest_ref="manifest.synthetic.support",
            policy_assignment_key="policy.synthetic",
            policy_assignment_version="0.1.0",
            rule_set_key="rules.synthetic",
            rule_set_version="0.1.0",
        )
    return mode_id


def _grant(
    environment: PostgreSQLEnvironment,
    tenant: Tenant,
    capability: str,
    identity: str,
) -> ProfessionalAuthority:
    grant_id = uuid7()
    with environment.owner_engine.begin() as connection:
        connection.execute(
            sa.text(
                "INSERT INTO workspace.support_professional_grants "
                "(organization_id,workspace_id,grant_id,grant_version,human_identity_id,capability,professional_qualification_ref,authority_reference,status,effective_from,integrity_digest) "
                "VALUES (:o,:w,:grant,1,:identity,:capability,'qualification:synthetic-support@1','authority:synthetic-support@1','active',CURRENT_TIMESTAMP,:digest)"
            ),
            {
                "o": tenant.organization_id,
                "w": tenant.workspace_id,
                "grant": grant_id,
                "identity": identity,
                "capability": capability,
                "digest": DIGEST,
            },
        )
    return ProfessionalAuthority(
        identity,
        grant_id,
        1,
        capability,
        "qualification:synthetic-support@1",
    )


def _start_support(
    environment: PostgreSQLEnvironment, tenant: Tenant
) -> tuple[PostgresSupportProcess, UUID, ProfessionalAuthority]:
    lifecycle = PostgresLifecycleRepository(environment.lifecycle_engine)
    transition(lifecycle, tenant, 1, LifecycleState.ACTIVE, f"wp13-active-{tenant.workspace_id}")
    mode_id = _create_support_mode(environment, tenant)
    rule_set_id, _, _, _ = _seed_rule(environment, tenant)
    authority = _grant(
        environment,
        tenant,
        "support.scope.configure",
        "human:synthetic-support-scope-owner",
    )
    process_id = uuid7()
    scope = SupportScope(
        tenant.organization_id,
        tenant.workspace_id,
        mode_id,
        process_id,
        rule_set_id,
        "support.process@1.0.0",
        "authority.synthetic@1.0.0",
        "1.3.0",
        ("retention.synthetic@0.1.0", "confirmation.synthetic@0.1.0"),
        (
            "id_package",
            "executive_scheme",
            "presented_volume_trace",
            "ks_payment_trace",
        ),
        "synthetic_non_confidential",
    )
    service = PostgresSupportProcess(environment.support_engine)
    command = StartSupportProcess(
        uuid7(),
        scope,
        ("pd_rd", "contract", "customer_regulation", "field_evidence"),
        DIGEST,
        authority,
        f"support-start-{process_id}",
        uuid7(),
        uuid7(),
    )
    outcome = service.start(context=_support_context(tenant), command=command)
    assert outcome.state is SupportState.SCOPE_CONFIGURED
    replay = service.start(context=_support_context(tenant), command=command)
    assert replay.outcome == "duplicate_completed"
    assert replay.revision == outcome.revision
    assert replay.state is outcome.state
    return service, process_id, authority


def test_wp13_schema_roles_rls_and_migration_head(
    postgres_environment: PostgreSQLEnvironment,
) -> None:
    inspector = sa.inspect(postgres_environment.owner_engine)
    assert {
        "support_processes",
        "support_material_admissions",
        "support_control_results",
        "support_generation_runs",
        "support_executive_scheme_versions",
        "support_payment_readiness",
        "support_terminal_outcomes",
    } <= set(inspector.get_table_names(schema="workspace"))
    assert {"template_sources", "template_versions", "field_schema_versions"} <= set(
        inspector.get_table_names(schema="platform")
    )
    with postgres_environment.owner_engine.connect() as connection:
        assert (
            connection.scalar(sa.text("SELECT version_num FROM alembic_version"))
            == "0026_support_id_finalize"
        )
        assert (
            connection.scalar(
                sa.text("SELECT rolname FROM pg_roles WHERE rolname='asd_support_service'")
            )
            == "asd_support_service"
        )
        assert (
            connection.scalar(
                sa.text(
                    "SELECT has_table_privilege('asd_support_service','workspace.support_professional_grants','INSERT')"
                )
            )
            is False
        )
        policies = int(
            connection.scalar(
                sa.text(
                    "SELECT count(*) FROM pg_policies WHERE schemaname='workspace' "
                    "AND tablename LIKE 'support_%'"
                )
            )
            or 0
        )
    assert policies >= 25


def test_support_process_idempotency_concurrency_rls_and_lifecycle_fence(
    postgres_environment: PostgreSQLEnvironment,
) -> None:
    tenant_a = create_tenant(postgres_environment)
    tenant_b = create_tenant(postgres_environment, tenant_a.organization_id)
    service, process_id, _ = _start_support(postgres_environment, tenant_a)
    work_authority = _grant(
        postgres_environment,
        tenant_a,
        "support.work.plan",
        "human:synthetic-pto-planner",
    )
    command = SupportCommand(
        uuid7(),
        SupportCommandType.CREATE_PLANNED_WORK,
        process_id,
        1,
        f"planned-work-{process_id}",
        uuid7(),
        uuid7(),
        {"work_instance_ref": "work:synthetic@1", "fact_state": "planned"},
        work_authority,
    )
    accepted = service.execute(context=_support_context(tenant_a), command=command)
    replay = service.execute(context=_support_context(tenant_a), command=command)
    assert accepted.revision == replay.revision == 2
    assert accepted.state is replay.state is SupportState.EXECUTING
    with pytest.raises(SupportError) as conflict:
        service.execute(
            context=_support_context(tenant_a),
            command=replace(command, command_id=uuid7(), idempotency_key="stale-revision"),
        )
    assert conflict.value.code is SupportErrorCode.CONCURRENCY_CONFLICT

    with postgres_environment.support_engine.begin() as connection:
        connection.execute(
            sa.select(
                sa.func.set_config("asd.organization_id", str(tenant_b.organization_id), True),
                sa.func.set_config("asd.workspace_id", str(tenant_b.workspace_id), True),
            )
        )
        assert connection.scalar(sa.text("SELECT count(*) FROM workspace.support_processes")) == 0
        with pytest.raises(DBAPIError):
            connection.execute(
                sa.text(
                    "INSERT INTO workspace.support_professional_grants "
                    "(organization_id,workspace_id,grant_id,grant_version,human_identity_id,capability,professional_qualification_ref,authority_reference,status,effective_from,integrity_digest) "
                    "VALUES (:o,:w,:grant,1,'human:forbidden','support.work.plan','qualification:forbidden','authority:forbidden','active',CURRENT_TIMESTAMP,:digest)"
                ),
                {
                    "o": tenant_b.organization_id,
                    "w": tenant_b.workspace_id,
                    "grant": uuid7(),
                    "digest": DIGEST,
                },
            )

    lifecycle = PostgresLifecycleRepository(postgres_environment.lifecycle_engine)
    transition(lifecycle, tenant_a, 2, LifecycleState.FREEZING, "wp13-freeze")
    late = replace(
        command,
        command_id=uuid7(),
        expected_revision=2,
        idempotency_key="late-after-freeze",
    )
    with pytest.raises(SupportError) as fenced:
        service.execute(context=_support_context(tenant_a), command=late)
    assert fenced.value.code is SupportErrorCode.WORKSPACE_FENCED


def test_support_reset_is_scoped_and_platform_templates_survive(
    postgres_environment: PostgreSQLEnvironment,
    tmp_path: Path,
) -> None:
    tenant_a = create_tenant(postgres_environment)
    tenant_b = create_tenant(postgres_environment, tenant_a.organization_id)
    _, process_a, _ = _start_support(postgres_environment, tenant_a)
    _, process_b, _ = _start_support(postgres_environment, tenant_b)
    template_source = uuid7()
    with postgres_environment.owner_engine.begin() as connection:
        connection.execute(
            sa.text(
                "INSERT INTO platform.template_sources "
                "(template_source_id,stable_key,format,source_kind,source_digest,provenance_ref,rights_status,authority_status,created_at) "
                "VALUES (:id,:key,'DOCX','synthetic_qualification',:digest,'provenance:synthetic','synthetic_permitted','candidate',CURRENT_TIMESTAMP)"
            ),
            {
                "id": template_source,
                "key": f"template.synthetic.{template_source}",
                "digest": DIGEST,
            },
        )
    archive_payload = json.dumps(
        {
            "workspace_id": str(tenant_a.workspace_id),
            "support_process_id": str(process_a),
            "contract_version": "1.3.0",
            "deliverable_scope": ["id_package", "executive_scheme", "ks_payment_trace"],
        },
        sort_keys=True,
    ).encode()
    archive_service = PortableArchiveService()
    archive_path = tmp_path / "support-portable-archive.zip"
    archive = archive_service.create(
        package_id=uuid7(),
        organization_id=tenant_a.organization_id,
        construction_object_id=tenant_a.construction_object_id,
        workspace_id=tenant_a.workspace_id,
        workspace_revision=1,
        contract_versions={"support": "1.3.0"},
        policy_versions={"retention": "0.1.0"},
        rule_set_version="0.1.0",
        entries=(
            ArchiveEntry(
                "support/manifest.json",
                f"support-process:{process_a}:1",
                archive_payload,
                "application/json",
            ),
        ),
        destination=archive_path,
    )
    verified_archive = archive_service.verify(archive.package_path)
    assert verified_archive.manifest_digest == archive.manifest_digest
    assert verified_archive.item_count == 1
    definition = StorageAdapterDefinition(
        "workspace.postgresql",
        "1.0.0",
        "canonical",
        "workspace",
        "workspace",
        True,
        True,
        True,
        True,
        True,
        "1.0.0",
    )
    adapter = PostgresWorkspaceStorageAdapter(
        postgres_environment.destruction_engine,
        tenant_a.organization_id,
        definition,
    )
    support_items = tuple(
        item for item in adapter.inventory(tenant_a.workspace_id) if "support_" in item.item_id
    )
    assert support_items
    operation_id = uuid7()
    for item in adapter.inventory(tenant_a.workspace_id):
        adapter.purge_item(
            workspace_id=tenant_a.workspace_id,
            item_id=item.item_id,
            operation_id=operation_id,
        )
    assert adapter.inventory(tenant_a.workspace_id) == ()
    with postgres_environment.owner_engine.connect() as connection:
        assert (
            connection.scalar(
                sa.text(
                    "SELECT count(*) FROM workspace.support_processes "
                    "WHERE organization_id=:o AND workspace_id=:w AND support_process_id=:process"
                ),
                {"o": tenant_b.organization_id, "w": tenant_b.workspace_id, "process": process_b},
            )
            == 1
        )
        assert (
            connection.scalar(
                sa.text(
                    "SELECT count(*) FROM platform.template_sources WHERE template_source_id=:id"
                ),
                {"id": template_source},
            )
            == 1
        )
        assert (
            connection.scalar(
                sa.text(
                    "SELECT count(*) FROM workspace.support_processes WHERE support_process_id=:process"
                ),
                {"process": process_a},
            )
            == 0
        )


def test_disposable_0007_to_0006_to_0007(
    postgres_environment: PostgreSQLEnvironment, repository_root: object
) -> None:
    suffix = hashlib.sha256(os.urandom(16)).hexdigest()[:12]
    database_name = f"asd_g04_test_wp13_{suffix}"
    cluster = sa.create_engine(
        postgres_environment.cluster_admin_url,
        isolation_level="AUTOCOMMIT",
    )
    create_database(cluster, database_name)
    database_url = postgres_environment.cluster_admin_url.set(database=database_name)
    try:
        run_migration(str(repository_root), database_url, "head")
        os.environ["ASD_ALLOW_DESTRUCTIVE_DOWNGRADE"] = "1"
        run_migration(str(repository_root), database_url, "0006_wp12")
        run_migration(str(repository_root), database_url, "head")
        with sa.create_engine(database_url).connect() as connection:
            assert (
                connection.scalar(sa.text("SELECT version_num FROM alembic_version"))
                == "0026_support_id_finalize"
            )
    finally:
        os.environ.pop("ASD_ALLOW_DESTRUCTIVE_DOWNGRADE", None)
        drop_database(cluster, database_name)
        cluster.dispose()
