# ruff: noqa: E501

from __future__ import annotations

import hashlib
import os
from dataclasses import replace
from datetime import UTC, datetime
from uuid import UUID

import pytest
import sqlalchemy as sa
from sqlalchemy.exc import DBAPIError

from asd_kontur.audit import PostgresCorpusAuditStore
from asd_kontur.corpus import CorpusScope, PageInspection, PhysicalObjectInspection
from asd_kontur.domain import uuid7
from asd_kontur.lifecycle import (
    AdapterHealth,
    LifecycleState,
    PostgresLifecycleRepository,
    PostgresWorkspaceStorageAdapter,
    StorageAdapterDefinition,
)
from asd_kontur.persistence import WorkspaceContext, WorkspaceUnitOfWork

from .conftest import PostgreSQLEnvironment, create_database, drop_database, run_migration
from .test_workspace_lifecycle import (
    Tenant,
    create_tenant,
    transition,
    workspace_context,
)

pytestmark = pytest.mark.postgres
DIGEST = "sha256:" + "a" * 64


def audit_context(tenant: Tenant) -> WorkspaceContext:
    return replace(
        workspace_context(tenant, service=True),
        service_identity_id="service:synthetic-audit",
    )


def set_scope(connection: sa.Connection, tenant: Tenant) -> None:
    connection.execute(
        sa.select(
            sa.func.set_config("asd.organization_id", str(tenant.organization_id), True),
            sa.func.set_config("asd.workspace_id", str(tenant.workspace_id), True),
        )
    ).one()


def activate(environment: PostgreSQLEnvironment, tenant: Tenant) -> None:
    transition(
        PostgresLifecycleRepository(environment.lifecycle_engine),
        tenant,
        1,
        LifecycleState.ACTIVE,
        f"wp14-active-{tenant.workspace_id}",
    )


def create_mode(environment: PostgreSQLEnvironment, tenant: Tenant, mode: str = "Audit") -> UUID:
    mode_id = uuid7()
    with WorkspaceUnitOfWork(environment.application_engine, workspace_context(tenant)) as unit:
        assert unit.workspaces is not None
        unit.workspaces.create_mode_execution(
            mode_execution_id=mode_id,
            mode=mode,
            purpose="purpose.synthetic.corpus-audit",
            input_manifest_ref="manifest.synthetic.corpus-audit",
            policy_assignment_key="policy.synthetic",
            policy_assignment_version="0.1.0",
            rule_set_key="rules.synthetic",
            rule_set_version="0.1.0",
            contract_version="1.4.0",
            schema_id="urn:asd-kontur:contracts:v1.4:schema:audit",
            schema_version="1.4.0",
        )
    return mode_id


def insert_mission(
    environment: PostgreSQLEnvironment, tenant: Tenant, mode_id: UUID, mission_id: UUID
) -> None:
    with environment.audit_engine.begin() as connection:
        set_scope(connection, tenant)
        connection.execute(
            sa.text(
                "INSERT INTO workspace.collection_missions "
                "(organization_id,workspace_id,collection_mission_id,mode_execution_id,state,revision,current_fingerprint,collector_identity_id,correlation_id,created_at,updated_at) "
                "VALUES (:o,:w,:mission,:mode,'collecting',1,:digest,'human:synthetic-collector',:correlation,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)"
            ),
            {
                "o": tenant.organization_id,
                "w": tenant.workspace_id,
                "mission": mission_id,
                "mode": mode_id,
                "digest": DIGEST,
                "correlation": uuid7(),
            },
        )


def test_wp14_schema_role_rls_and_force_rls(
    postgres_environment: PostgreSQLEnvironment,
) -> None:
    inspector = sa.inspect(postgres_environment.owner_engine)
    assert {
        "collection_missions",
        "physical_object_inspections",
        "corpus_processing_plan_versions",
        "corpus_processing_receipts",
        "logical_document_occurrences",
        "corpus_snapshot_versions",
        "audit_delta_versions",
        "audit_package_versions",
        "audit_action_request_versions",
        "audit_report_versions",
    } <= set(inspector.get_table_names(schema="workspace"))
    with postgres_environment.owner_engine.connect() as connection:
        assert (
            connection.scalar(sa.text("SELECT version_num FROM alembic_version"))
            == "0017_unified_harness"
        )
        assert (
            connection.scalar(
                sa.text("SELECT rolname FROM pg_roles WHERE rolname='asd_audit_service'")
            )
            == "asd_audit_service"
        )
        rls = connection.execute(
            sa.text(
                "SELECT relrowsecurity,relforcerowsecurity FROM pg_class c "
                "JOIN pg_namespace n ON n.oid=c.relnamespace "
                "WHERE n.nspname='workspace' AND c.relname='corpus_snapshot_versions'"
            )
        ).one()
    assert rls == (True, True)


def test_collection_pipeline_is_shared_by_all_four_modes(
    postgres_environment: PostgreSQLEnvironment,
) -> None:
    tenant = create_tenant(postgres_environment)
    activate(postgres_environment, tenant)
    mission_ids: list[UUID] = []
    for mode in ("Tender", "Support", "Audit", "Restoration"):
        mode_id = create_mode(postgres_environment, tenant, mode)
        mission_id = uuid7()
        insert_mission(postgres_environment, tenant, mode_id, mission_id)
        mission_ids.append(mission_id)
    with postgres_environment.audit_engine.begin() as connection:
        set_scope(connection, tenant)
        rows = tuple(
            connection.scalars(
                sa.text(
                    "SELECT collection_mission_id FROM workspace.collection_missions ORDER BY collection_mission_id"
                )
            )
        )
    assert set(rows) == set(mission_ids)


def test_default_deny_ab_isolation_and_cross_workspace_fk(
    postgres_environment: PostgreSQLEnvironment,
) -> None:
    tenant_a = create_tenant(postgres_environment)
    tenant_b = create_tenant(postgres_environment, tenant_a.organization_id)
    activate(postgres_environment, tenant_a)
    activate(postgres_environment, tenant_b)
    mode_a = create_mode(postgres_environment, tenant_a)
    mode_b = create_mode(postgres_environment, tenant_b)
    mission_a, mission_b = uuid7(), uuid7()
    insert_mission(postgres_environment, tenant_a, mode_a, mission_a)
    insert_mission(postgres_environment, tenant_b, mode_b, mission_b)
    with postgres_environment.audit_engine.connect() as connection:
        assert connection.scalar(sa.text("SELECT count(*) FROM workspace.collection_missions")) == 0
    with postgres_environment.audit_engine.begin() as connection:
        set_scope(connection, tenant_a)
        visible = tuple(
            connection.scalars(
                sa.text("SELECT collection_mission_id FROM workspace.collection_missions")
            )
        )
    assert visible == (mission_a,)
    with pytest.raises(DBAPIError):
        with postgres_environment.audit_engine.begin() as connection:
            set_scope(connection, tenant_b)
            connection.execute(
                sa.text(
                    "INSERT INTO workspace.collection_missions "
                    "(organization_id,workspace_id,collection_mission_id,mode_execution_id,state,revision,current_fingerprint,collector_identity_id,correlation_id,created_at,updated_at) "
                    "VALUES (:o,:w,:mission,:mode,'collecting',1,:digest,'human:collector',:correlation,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)"
                ),
                {
                    "o": tenant_b.organization_id,
                    "w": tenant_b.workspace_id,
                    "mission": uuid7(),
                    "mode": mode_a,
                    "digest": DIGEST,
                    "correlation": uuid7(),
                },
            )


def test_inspection_repository_is_scoped_immutable_and_lifecycle_fenced(
    postgres_environment: PostgreSQLEnvironment,
) -> None:
    tenant = create_tenant(postgres_environment)
    activate(postgres_environment, tenant)
    object_id = uuid7()
    with WorkspaceUnitOfWork(
        postgres_environment.application_engine, workspace_context(tenant)
    ) as unit:
        assert unit.workspaces is not None
        unit.workspaces.add_object(
            object_id=object_id,
            content_digest=DIGEST,
            size_bytes=128,
            object_class="collected_source",
        )
    inspection = PhysicalObjectInspection(
        CorpusScope(tenant.organization_id, tenant.workspace_id),
        uuid7(),
        object_id,
        1,
        DIGEST,
        128,
        "application/pdf",
        False,
        True,
        1,
        (PageInspection(1, 595.0, 842.0, 0, 100, 0),),
        0,
        0,
        "preflight-1.0.0",
        datetime.now(UTC),
    )
    store = PostgresCorpusAuditStore(postgres_environment.audit_engine)
    store.record_inspection(audit_context(tenant), inspection)
    with postgres_environment.audit_engine.begin() as connection:
        set_scope(connection, tenant)
        assert (
            connection.scalar(sa.text("SELECT count(*) FROM workspace.corpus_page_manifests")) == 1
        )
        with pytest.raises(DBAPIError):
            connection.execute(
                sa.text(
                    "UPDATE workspace.physical_object_inspections SET media_type='text/plain' WHERE inspection_id=:inspection"
                ),
                {"inspection": inspection.inspection_id},
            )
    lifecycle = PostgresLifecycleRepository(postgres_environment.lifecycle_engine)
    transition(lifecycle, tenant, 2, LifecycleState.FREEZING, "wp14-freezing")
    second = replace(inspection, inspection_id=uuid7())
    with pytest.raises(DBAPIError):
        store.record_inspection(audit_context(tenant), second)


def test_header_updates_require_operation_context_and_exact_revision(
    postgres_environment: PostgreSQLEnvironment,
) -> None:
    tenant = create_tenant(postgres_environment)
    activate(postgres_environment, tenant)
    mode = create_mode(postgres_environment, tenant)
    mission = uuid7()
    insert_mission(postgres_environment, tenant, mode, mission)
    with pytest.raises(DBAPIError):
        with postgres_environment.audit_engine.begin() as connection:
            set_scope(connection, tenant)
            connection.execute(
                sa.text(
                    "UPDATE workspace.collection_missions SET state='reconciling',revision=2 WHERE collection_mission_id=:mission"
                ),
                {"mission": mission},
            )
    with postgres_environment.audit_engine.begin() as connection:
        set_scope(connection, tenant)
        connection.execute(sa.select(sa.func.set_config("asd.audit_operation_id", "op-1", True)))
        connection.execute(
            sa.text(
                "UPDATE workspace.collection_missions SET state='reconciling',revision=2 WHERE collection_mission_id=:mission"
            ),
            {"mission": mission},
        )
    with pytest.raises(DBAPIError):
        with postgres_environment.audit_engine.begin() as connection:
            set_scope(connection, tenant)
            connection.execute(
                sa.select(sa.func.set_config("asd.audit_operation_id", "op-2", True))
            )
            connection.execute(
                sa.text(
                    "UPDATE workspace.collection_missions SET state='snapshotted',revision=4 WHERE collection_mission_id=:mission"
                ),
                {"mission": mission},
            )


def test_storage_inventory_and_exact_reset_preserve_workspace_b_and_platform(
    postgres_environment: PostgreSQLEnvironment,
) -> None:
    tenant_a = create_tenant(postgres_environment)
    tenant_b = create_tenant(postgres_environment, tenant_a.organization_id)
    activate(postgres_environment, tenant_a)
    activate(postgres_environment, tenant_b)
    mission_a, mission_b = uuid7(), uuid7()
    insert_mission(
        postgres_environment, tenant_a, create_mode(postgres_environment, tenant_a), mission_a
    )
    insert_mission(
        postgres_environment, tenant_b, create_mode(postgres_environment, tenant_b), mission_b
    )
    profile_id = uuid7()
    with postgres_environment.owner_engine.begin() as connection:
        connection.execute(
            sa.text(
                "INSERT INTO platform.corpus_processing_profile_versions "
                "(processing_profile_id,version,purpose,policy_digest,max_local_pages,max_local_bytes,max_pages_per_shard,max_raster_pages_per_shard,external_egress_state,assurance_class,created_at) "
                "VALUES (:profile,'development-1.0.0','synthetic-audit',:digest,50,52428800,100,10,'denied','development_synthetic',CURRENT_TIMESTAMP)"
            ),
            {"profile": profile_id, "digest": DIGEST},
        )
    definition = StorageAdapterDefinition(
        "postgres.workspace",
        "1.4.0",
        "postgresql",
        "authoritative",
        "workspace",
        True,
        True,
        True,
        True,
        True,
        "1.0.0",
        AdapterHealth.AVAILABLE,
    )
    adapter = PostgresWorkspaceStorageAdapter(
        postgres_environment.destruction_engine, tenant_a.organization_id, definition
    )
    inventory = {item.item_id for item in adapter.inventory(tenant_a.workspace_id)}
    assert "workspace.collection_missions" in inventory
    assert "workspace.audit_report_versions" in adapter.TABLES
    receipt = adapter.purge_item(
        workspace_id=tenant_a.workspace_id,
        item_id="workspace.collection_missions",
        operation_id=uuid7(),
    )
    assert receipt.after_count == 0
    with postgres_environment.owner_engine.connect() as connection:
        assert (
            connection.scalar(
                sa.text(
                    "SELECT count(*) FROM workspace.collection_missions WHERE workspace_id=:workspace"
                ),
                {"workspace": tenant_b.workspace_id},
            )
            == 1
        )
        assert (
            connection.scalar(
                sa.text(
                    "SELECT count(*) FROM platform.corpus_processing_profile_versions WHERE processing_profile_id=:profile"
                ),
                {"profile": profile_id},
            )
            == 1
        )


def test_disposable_0008_to_0007_to_0008(
    postgres_environment: PostgreSQLEnvironment, repository_root: object
) -> None:
    suffix = hashlib.sha256(os.urandom(16)).hexdigest()[:12]
    database_name = f"asd_g04_test_wp14_{suffix}"
    cluster = sa.create_engine(
        postgres_environment.cluster_admin_url,
        isolation_level="AUTOCOMMIT",
    )
    create_database(cluster, database_name)
    database_url = postgres_environment.cluster_admin_url.set(database=database_name)
    try:
        run_migration(str(repository_root), database_url, "head")
        os.environ["ASD_ALLOW_DESTRUCTIVE_DOWNGRADE"] = "1"
        run_migration(str(repository_root), database_url, "0007_wp13")
        run_migration(str(repository_root), database_url, "head")
        with sa.create_engine(database_url).connect() as connection:
            assert (
                connection.scalar(sa.text("SELECT version_num FROM alembic_version"))
                == "0017_unified_harness"
            )
    finally:
        os.environ.pop("ASD_ALLOW_DESTRUCTIVE_DOWNGRADE", None)
        drop_database(cluster, database_name)
        cluster.dispose()
