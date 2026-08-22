from __future__ import annotations

import os
import uuid
from dataclasses import dataclass

import pytest
import sqlalchemy as sa
from sqlalchemy.exc import DBAPIError, IntegrityError, ProgrammingError

from asd_kontur.domain import uuid7
from asd_kontur.persistence import (
    ObjectAdmission,
    ObjectAdmissionService,
    OrganizationContext,
    OrganizationUnitOfWork,
    WorkspaceContext,
    WorkspaceUnitOfWork,
)
from asd_kontur.persistence.errors import OptimisticConcurrencyError
from asd_kontur.persistence.tables import (
    mode_executions,
    outbox_records,
    workspace_audit_records,
    workspace_objects,
)

from .conftest import PostgreSQLEnvironment, create_database, drop_database, run_migration

pytestmark = pytest.mark.postgres


@dataclass(frozen=True, slots=True)
class Tenant:
    organization_id: uuid.UUID
    construction_object_id: uuid.UUID
    workspace_id: uuid.UUID


def _organization_context(organization_id: uuid.UUID) -> OrganizationContext:
    return OrganizationContext(
        organization_id=organization_id,
        actor_identity_id="identity.synthetic.architect",
        service_identity_id=None,
        correlation_id=uuid7(),
    )


def _workspace_context(tenant: Tenant) -> WorkspaceContext:
    return WorkspaceContext(
        organization_id=tenant.organization_id,
        workspace_id=tenant.workspace_id,
        actor_identity_id="identity.synthetic.architect",
        service_identity_id=None,
        correlation_id=uuid7(),
    )


def _create_tenant(environment: PostgreSQLEnvironment) -> Tenant:
    tenant = Tenant(uuid7(), uuid7(), uuid7())
    with OrganizationUnitOfWork(
        environment.application_engine,
        _organization_context(tenant.organization_id),
    ) as unit:
        assert unit.organizations is not None
        unit.organizations.add_organization(
            organization_id=tenant.organization_id,
            display_name="Synthetic organization",
        )
        unit.organizations.add_construction_object(
            construction_object_id=tenant.construction_object_id,
            display_name="Synthetic construction object",
        )
    with WorkspaceUnitOfWork(environment.application_engine, _workspace_context(tenant)) as unit:
        assert unit.workspaces is not None
        unit.workspaces.create_workspace(
            construction_object_id=tenant.construction_object_id,
            retention_profile_key="retention.synthetic",
            retention_profile_version="0.1.0",
            policy_assignment_key="policy.synthetic",
            policy_assignment_version="0.1.0",
            rule_set_key="rules.synthetic",
            rule_set_version="0.1.0",
        )
    return tenant


def _create_mode(environment: PostgreSQLEnvironment, tenant: Tenant) -> uuid.UUID:
    mode_id = uuid7()
    with WorkspaceUnitOfWork(environment.application_engine, _workspace_context(tenant)) as unit:
        assert unit.workspaces is not None
        unit.workspaces.create_mode_execution(
            mode_execution_id=mode_id,
            mode="Tender",
            purpose="purpose.synthetic.contract-review",
            input_manifest_ref="manifest.synthetic.001",
            policy_assignment_key="policy.synthetic",
            policy_assignment_version="0.1.0",
            rule_set_key="rules.synthetic",
            rule_set_version="0.1.0",
        )
    return mode_id


def test_clean_upgrade_created_required_schemas_tables_and_rls(
    postgres_environment: PostgreSQLEnvironment,
) -> None:
    inspector = sa.inspect(postgres_environment.owner_engine)
    assert {"platform", "organization", "workspace", "audit", "messaging"} <= set(
        inspector.get_schema_names()
    )
    assert {"organizations", "construction_objects"} <= set(
        inspector.get_table_names(schema="organization")
    )
    assert {"workspaces", "workspace_revisions", "mode_executions", "objects"} <= set(
        inspector.get_table_names(schema="workspace")
    )
    with postgres_environment.owner_engine.connect() as connection:
        count = connection.scalar(sa.text("SELECT count(*) FROM platform.contract_schema_versions"))
        app_role = connection.execute(
            sa.text("SELECT rolname, rolsuper FROM pg_roles WHERE rolname = :role"),
            {"role": postgres_environment.application_role},
        ).one()
        rls = connection.execute(
            sa.text(
                "SELECT relrowsecurity, relforcerowsecurity FROM pg_class c "
                "JOIN pg_namespace n ON n.oid = c.relnamespace "
                "WHERE n.nspname = 'workspace' AND c.relname = 'mode_executions'"
            )
        ).one()
    assert count == 13
    assert app_role.rolname == postgres_environment.application_role
    assert app_role.rolsuper is False
    assert tuple(rls) == (True, True)


def test_organization_and_workspace_rls_isolation(
    postgres_environment: PostgreSQLEnvironment,
) -> None:
    tenant_a = _create_tenant(postgres_environment)
    tenant_b = _create_tenant(postgres_environment)
    mode_a = _create_mode(postgres_environment, tenant_a)
    _create_mode(postgres_environment, tenant_b)

    with OrganizationUnitOfWork(
        postgres_environment.application_engine,
        _organization_context(tenant_a.organization_id),
    ) as unit:
        assert unit.organizations is not None
        assert unit.organizations.list_organization_ids() == [tenant_a.organization_id]
    with WorkspaceUnitOfWork(
        postgres_environment.application_engine,
        _workspace_context(tenant_a),
    ) as unit:
        assert unit.workspaces is not None
        assert unit.workspaces.list_mode_execution_ids() == [mode_a]


def test_missing_scope_denies_and_pool_does_not_leak_scope(
    postgres_environment: PostgreSQLEnvironment,
) -> None:
    tenant = _create_tenant(postgres_environment)
    _create_mode(postgres_environment, tenant)
    with WorkspaceUnitOfWork(postgres_environment.application_engine, _workspace_context(tenant)):
        pass

    with postgres_environment.application_engine.begin() as connection:
        settings = connection.execute(
            sa.text(
                "SELECT current_setting('asd.organization_id', true), "
                "current_setting('asd.workspace_id', true)"
            )
        ).one()
        visible = connection.scalar(sa.select(sa.func.count()).select_from(mode_executions))
    assert tuple(settings) in {(None, None), ("", "")}
    assert visible == 0

    with pytest.raises(DBAPIError):
        with postgres_environment.application_engine.begin() as connection:
            connection.execute(
                mode_executions.insert().values(
                    organization_id=tenant.organization_id,
                    workspace_id=tenant.workspace_id,
                    mode_execution_id=uuid7(),
                    mode="Tender",
                    purpose="purpose.synthetic",
                    state="requested",
                    revision=1,
                    input_manifest_ref="manifest.synthetic",
                    contract_key="mode.execution-request",
                    contract_version="0.1.0",
                    schema_id="urn:asd-kontur:contracts:v0.1:schema:mode-deliverable",
                    schema_version="0.1.0",
                    policy_assignment_key="policy.synthetic",
                    policy_assignment_version="0.1.0",
                    rule_set_key="rules.synthetic",
                    rule_set_version="0.1.0",
                    retention_class="workspace.mode-execution",
                    created_by_identity_id="identity.synthetic",
                    correlation_id=uuid7(),
                )
            )


def test_composite_fk_blocks_cross_workspace_object_link(
    postgres_environment: PostgreSQLEnvironment,
) -> None:
    tenant_a = _create_tenant(postgres_environment)
    tenant_b = Tenant(tenant_a.organization_id, tenant_a.construction_object_id, uuid7())
    with WorkspaceUnitOfWork(
        postgres_environment.application_engine, _workspace_context(tenant_b)
    ) as unit:
        assert unit.workspaces is not None
        unit.workspaces.create_workspace(
            construction_object_id=tenant_b.construction_object_id,
            retention_profile_key="retention.synthetic",
            retention_profile_version="0.1.0",
            policy_assignment_key="policy.synthetic",
            policy_assignment_version="0.1.0",
            rule_set_key="rules.synthetic",
            rule_set_version="0.1.0",
        )
    object_a, object_b = uuid7(), uuid7()
    digest = "sha256:" + "1" * 64
    with WorkspaceUnitOfWork(
        postgres_environment.application_engine, _workspace_context(tenant_a)
    ) as unit:
        assert unit.workspaces is not None
        unit.workspaces.add_object(object_id=object_a, content_digest=digest)
    with WorkspaceUnitOfWork(
        postgres_environment.application_engine, _workspace_context(tenant_b)
    ) as unit:
        assert unit.workspaces is not None
        unit.workspaces.add_object(object_id=object_b, content_digest=digest)

    with pytest.raises(IntegrityError):
        with WorkspaceUnitOfWork(
            postgres_environment.application_engine,
            _workspace_context(tenant_a),
        ) as unit:
            assert unit.workspaces is not None
            unit.workspaces.link_objects(
                link_id=uuid7(),
                source_object_id=object_a,
                target_object_id=object_b,
                relation_kind="evidence_for",
            )


def test_optimistic_concurrency_and_idempotent_retry(
    postgres_environment: PostgreSQLEnvironment,
) -> None:
    tenant = _create_tenant(postgres_environment)
    mode_id = _create_mode(postgres_environment, tenant)
    context = _workspace_context(tenant)
    with WorkspaceUnitOfWork(postgres_environment.application_engine, context) as unit:
        assert unit.workspaces is not None
        assert (
            unit.workspaces.update_mode_state(
                mode_execution_id=mode_id,
                expected_revision=1,
                new_state="running",
            )
            == 2
        )
    with pytest.raises(OptimisticConcurrencyError):
        with WorkspaceUnitOfWork(postgres_environment.application_engine, context) as unit:
            assert unit.workspaces is not None
            unit.workspaces.update_mode_state(
                mode_execution_id=mode_id,
                expected_revision=1,
                new_state="blocked",
            )

    command_id = uuid7()
    digest = "sha256:" + "2" * 64
    with WorkspaceUnitOfWork(postgres_environment.application_engine, context) as unit:
        assert unit.messaging is not None
        first = unit.messaging.claim_idempotency(
            handler_key="mode.start",
            idempotency_key="idempotency.synthetic.001",
            semantic_digest=digest,
            command_id=command_id,
        )
    with WorkspaceUnitOfWork(postgres_environment.application_engine, context) as unit:
        assert unit.messaging is not None
        replay = unit.messaging.claim_idempotency(
            handler_key="mode.start",
            idempotency_key="idempotency.synthetic.001",
            semantic_digest=digest,
            command_id=uuid7(),
        )
    assert first.is_new is True
    assert replay.is_new is False
    assert replay.command_id == command_id

    message_id = uuid7()
    with WorkspaceUnitOfWork(postgres_environment.application_engine, context) as unit:
        assert unit.messaging is not None
        accepted = unit.messaging.record_inbox(
            consumer_key="projection.synthetic",
            message_id=message_id,
            payload_digest="sha256:" + "7" * 64,
            contract_key="event.integration",
            contract_version="0.1.0",
            schema_id="urn:asd-kontur:contracts:v0.1:schema:message",
            schema_version="0.1.0",
        )
    with WorkspaceUnitOfWork(postgres_environment.application_engine, context) as unit:
        assert unit.messaging is not None
        duplicate_requires_reconciliation = not unit.messaging.record_inbox(
            consumer_key="projection.synthetic",
            message_id=message_id,
            payload_digest="sha256:" + "7" * 64,
            contract_key="event.integration",
            contract_version="0.1.0",
            schema_id="urn:asd-kontur:contracts:v0.1:schema:message",
            schema_version="0.1.0",
        )
    assert accepted is True
    assert duplicate_requires_reconciliation is True


def test_audit_is_append_only_for_application_role(
    postgres_environment: PostgreSQLEnvironment,
) -> None:
    tenant = _create_tenant(postgres_environment)
    audit_id = uuid7()
    context = _workspace_context(tenant)
    with WorkspaceUnitOfWork(postgres_environment.application_engine, context) as unit:
        assert unit.audit is not None
        unit.audit.append(
            audit_record_id=audit_id,
            capability="workspace.inspect",
            operation="mode.request",
            outcome_code="accepted_pending",
            contract_key="command.outcome",
            contract_version="0.1.0",
            policy_key="policy.synthetic",
            policy_version="0.1.0",
            safe_message_key="audit.synthetic.accepted",
            record_digest="sha256:" + "3" * 64,
        )
    for statement in (
        workspace_audit_records.update().values(outcome_code="changed"),
        workspace_audit_records.delete(),
    ):
        with pytest.raises(ProgrammingError):
            with WorkspaceUnitOfWork(postgres_environment.application_engine, context) as unit:
                assert unit.session is not None
                unit.session.execute(statement)


def test_canonical_change_and_outbox_are_atomic_and_rollback_is_clean(
    postgres_environment: PostgreSQLEnvironment,
) -> None:
    tenant = _create_tenant(postgres_environment)
    context = _workspace_context(tenant)
    object_id = uuid7()
    event_id = uuid7()
    admission = ObjectAdmission(
        object_id=object_id,
        content_digest="sha256:" + "6" * 64,
        size_bytes=42,
        command_id=uuid7(),
        idempotency_key="idempotency.synthetic.object-admission",
        semantic_digest="sha256:" + "4" * 64,
        outbox_record_id=uuid7(),
        event_id=event_id,
    )
    service = ObjectAdmissionService(postgres_environment.application_engine)
    first = service.admit(context=context, admission=admission)
    replay = service.admit(context=context, admission=admission)
    with WorkspaceUnitOfWork(postgres_environment.application_engine, context) as unit:
        assert unit.session is not None
        canonical = unit.session.scalar(
            sa.select(sa.func.count())
            .select_from(workspace_objects)
            .where(workspace_objects.c.object_id == object_id)
        )
        outbox = unit.session.scalar(
            sa.select(sa.func.count())
            .select_from(outbox_records)
            .where(outbox_records.c.event_id == event_id)
        )
    assert (canonical, outbox) == (1, 1)
    assert first.is_new is True
    assert replay.is_new is False

    rolled_back_object = uuid7()
    with pytest.raises(RuntimeError, match="synthetic rollback"):
        with WorkspaceUnitOfWork(postgres_environment.application_engine, context) as unit:
            assert unit.workspaces is not None
            unit.workspaces.add_object(
                object_id=rolled_back_object,
                content_digest="sha256:" + "5" * 64,
            )
            raise RuntimeError("synthetic rollback")
    with WorkspaceUnitOfWork(postgres_environment.application_engine, context) as unit:
        assert unit.session is not None
        count = unit.session.scalar(
            sa.select(sa.func.count())
            .select_from(workspace_objects)
            .where(workspace_objects.c.object_id == rolled_back_object)
        )
    assert count == 0


def test_disposable_downgrade_upgrade_round_trip(
    postgres_environment: PostgreSQLEnvironment,
    repository_root: object,
) -> None:
    secondary = f"asd_g04_test_roundtrip_{os.getpid()}"
    cluster_engine = sa.create_engine(
        postgres_environment.cluster_admin_url,
        isolation_level="AUTOCOMMIT",
    )
    create_database(cluster_engine, secondary)
    secondary_url = postgres_environment.cluster_admin_url.set(database=secondary)
    try:
        run_migration(str(repository_root), secondary_url, "head")
        previous = os.environ.get("ASD_ALLOW_DESTRUCTIVE_DOWNGRADE")
        os.environ["ASD_ALLOW_DESTRUCTIVE_DOWNGRADE"] = "1"
        try:
            run_migration(str(repository_root), secondary_url, "base")
        finally:
            if previous is None:
                os.environ.pop("ASD_ALLOW_DESTRUCTIVE_DOWNGRADE", None)
            else:
                os.environ["ASD_ALLOW_DESTRUCTIVE_DOWNGRADE"] = previous
        run_migration(str(repository_root), secondary_url, "head")
        inspector = sa.inspect(sa.create_engine(secondary_url))
        assert "workspaces" in inspector.get_table_names(schema="workspace")
    finally:
        drop_database(cluster_engine, secondary)
        cluster_engine.dispose()
