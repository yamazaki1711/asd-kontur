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

from asd_kontur.audit import (
    AuditCommand,
    AuditCommandType,
    AuditScope,
    CausalImpactPath,
    CausalReadinessDelta,
    DeltaDenominator,
    DeltaState,
    DocumentDelta,
    EvidenceRatedItem,
    PackageAssessment,
    PackageReadiness,
    PostgresCorpusAuditStore,
    ProcessState,
)
from asd_kontur.corpus import (
    CorpusCoverage,
    CorpusOutcome,
    CorpusReconciliation,
    CorpusScope,
    CorpusSnapshot,
    PageInspection,
    PhysicalObjectInspection,
    PhysicalObjectRef,
    ResourcePolicy,
    build_processing_plan,
)
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
from .test_common_domain_kernel import _seed_rule
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


def _seed_processing_profile(environment: PostgreSQLEnvironment) -> UUID:
    profile_id = uuid7()
    with environment.owner_engine.begin() as connection:
        connection.execute(
            sa.text(
                "INSERT INTO platform.corpus_processing_profile_versions "
                "(processing_profile_id,version,purpose,policy_digest,max_local_pages,"
                "max_local_bytes,max_pages_per_shard,max_raster_pages_per_shard,"
                "external_egress_state,assurance_class,created_at) VALUES "
                "(:profile,'development-1.0.0','synthetic-audit',:digest,50,52428800,"
                "100,10,'denied','development_synthetic',CURRENT_TIMESTAMP)"
            ),
            {"profile": profile_id, "digest": DIGEST},
        )
    return profile_id


def _complete_snapshot_scope(environment: PostgreSQLEnvironment, tenant: Tenant) -> AuditScope:
    """Create the smallest reconciled snapshot through the actual Audit stores."""

    mode_id = create_mode(environment, tenant)
    mission_id = uuid7()
    insert_mission(environment, tenant, mode_id, mission_id)
    collection_scope_id = uuid7()
    with environment.audit_engine.begin() as connection:
        set_scope(connection, tenant)
        connection.execute(
            sa.text(
                "INSERT INTO workspace.collection_scope_versions "
                "(organization_id,workspace_id,collection_scope_id,version,"
                "collection_mission_id,included_locations,included_media,"
                "completeness_claim,authority_profile_version,fingerprint,created_at) "
                "VALUES (:o,:w,:scope,1,:mission,'[\"synthetic\"]'::jsonb,"
                "'[\"digital\"]'::jsonb,'claimed_complete','1.0.0',:digest,"
                "CURRENT_TIMESTAMP)"
            ),
            {
                "o": tenant.organization_id,
                "w": tenant.workspace_id,
                "scope": collection_scope_id,
                "mission": mission_id,
                "digest": DIGEST,
            },
        )
    object_id = uuid7()
    with WorkspaceUnitOfWork(environment.application_engine, workspace_context(tenant)) as unit:
        assert unit.workspaces is not None
        unit.workspaces.add_object(
            object_id=object_id,
            content_digest=DIGEST,
            size_bytes=128,
            object_class="synthetic_audit_source",
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
        (PageInspection(1, 595.0, 842.0, 0, 120, 0),),
        0,
        0,
        "preflight-1.0.0",
        datetime.now(UTC),
    )
    store = PostgresCorpusAuditStore(environment.audit_engine)
    context = audit_context(tenant)
    store.record_inspection(context, inspection)
    policy = ResourcePolicy("development-1.0.0", 50, 52428800, 100, 10, 1000, False, False)
    plan = build_processing_plan(
        inspection,
        purpose="synthetic-audit",
        classification="internal",
        policy=policy,
    )
    store.record_plan(context, plan, processing_profile_id=_seed_processing_profile(environment))
    reconciliation = CorpusReconciliation(
        inspection.scope,
        uuid7(),
        plan.processing_plan_id,
        plan.version,
        (1,),
        (1,),
        (),
        (),
        (),
        (),
        (),
        CorpusOutcome.COMPLETE,
        DIGEST,
    )
    store.record_reconciliation(context, reconciliation)
    rule_set_id, _, _, _ = _seed_rule(environment, tenant)
    snapshot = CorpusSnapshot(
        inspection.scope,
        uuid7(),
        1,
        collection_scope_id,
        1,
        (PhysicalObjectRef(object_id, 1),),
        ((inspection.inspection_id, 1),),
        (),
        (),
        (),
        (),
        CorpusCoverage(1, 1, 1, 1, 1, 0, 0, "coverage-1.0.0"),
        (reconciliation.reconciliation_id,),
        rule_set_id,
        datetime.now(UTC),
        CorpusOutcome.COMPLETE,
    )
    store.record_snapshot(context, snapshot)
    return AuditScope(
        tenant.organization_id,
        tenant.workspace_id,
        mode_id,
        uuid7(),
        snapshot.corpus_snapshot_id,
        snapshot.version,
        rule_set_id,
        "1.0.0",
        "1.0.0",
        "1.4.0",
    )


def test_wp14_schema_role_rls_and_force_rls(
    migration_head: str,
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
            connection.scalar(sa.text("SELECT version_num FROM alembic_version")) == migration_head
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


def test_audit_process_persists_exact_snapshot_and_all_declared_header_states(
    postgres_environment: PostgreSQLEnvironment,
) -> None:
    tenant = create_tenant(postgres_environment)
    activate(postgres_environment, tenant)
    scope = _complete_snapshot_scope(postgres_environment, tenant)
    context = audit_context(tenant)
    store = PostgresCorpusAuditStore(postgres_environment.audit_engine)

    store.start_audit_process(context, scope)
    # The exact immutable scope is a natural idempotency key: a safe retry
    # neither creates a second header nor changes its revision.
    store.start_audit_process(context, scope)
    with pytest.raises(ValueError, match="different immutable scope"):
        store.start_audit_process(context, replace(scope, contract_registry_version="1.4.1"))

    commands = (
        AuditCommandType.START_COLLECTION,
        AuditCommandType.RECONCILE_CORPUS,
        AuditCommandType.PUBLISH_CORPUS_SNAPSHOT,
        AuditCommandType.START_AUDIT,
    )
    revision = 1
    for command_type in commands:
        outcome = store.apply_command(
            context,
            AuditCommand(
                uuid7(),
                command_type,
                scope.audit_process_id,
                revision,
                f"audit-process:{scope.audit_process_id}:{revision}",
                "service:synthetic-audit",
                "audit.process.transition",
                uuid7(),
                uuid7(),
                DIGEST,
            ),
        )
        assert outcome.accepted
        revision = outcome.revision

    with postgres_environment.audit_engine.begin() as connection:
        set_scope(connection, tenant)
        row = connection.execute(
            sa.text(
                "SELECT state,revision,corpus_snapshot_id,corpus_snapshot_version,rule_set_version_id "
                "FROM workspace.audit_processes WHERE audit_process_id=:process"
            ),
            {"process": scope.audit_process_id},
        ).one()
    assert row == (
        ProcessState.EVALUATING.value,
        5,
        scope.corpus_snapshot_id,
        scope.corpus_snapshot_version,
        scope.rule_set_version_id,
    )

    stale = store.apply_command(
        context,
        AuditCommand(
            uuid7(),
            AuditCommandType.EVALUATE_DOCUMENT_DELTA,
            scope.audit_process_id,
            4,
            f"audit-process:{scope.audit_process_id}:stale",
            "service:synthetic-audit",
            "audit.process.transition",
            uuid7(),
            uuid7(),
            DIGEST,
        ),
    )
    assert not stale.accepted
    assert stale.outcome_code == "CONCURRENCY_CONFLICT"

    document_delta = DocumentDelta(
        uuid7(),
        1,
        scope,
        DeltaDenominator(
            uuid7(),
            1,
            ("synthetic-audit-scope",),
            ("required-act",),
            scope.rule_set_version_id,
            ("rule-trace:synthetic",),
        ),
        (
            EvidenceRatedItem(
                "required-act",
                DeltaState.MISSING,
                (),
                (),
                (),
                (),
                (),
                ("ACT_NOT_COLLECTED",),
                ("package_readiness",),
            ),
        ),
    )
    evaluated = store.evaluate_document_delta(
        context,
        AuditCommand(
            uuid7(),
            AuditCommandType.EVALUATE_DOCUMENT_DELTA,
            scope.audit_process_id,
            5,
            f"audit-process:{scope.audit_process_id}:document-delta",
            "service:synthetic-audit",
            "audit.document.evaluate",
            uuid7(),
            uuid7(),
            DIGEST,
        ),
        document_delta,
    )
    assert evaluated.accepted and evaluated.revision == 6
    with postgres_environment.audit_engine.begin() as connection:
        set_scope(connection, tenant)
        assert (
            connection.scalar(sa.text("SELECT count(*) FROM workspace.audit_delta_versions")) == 1
        )
        assert connection.scalar(sa.text("SELECT count(*) FROM workspace.audit_delta_items")) == 1
        assert (
            connection.scalar(
                sa.text(
                    "SELECT revision FROM workspace.audit_processes WHERE audit_process_id=:process"
                ),
                {"process": scope.audit_process_id},
            )
            == 6
        )
    repeated_evaluation = store.evaluate_document_delta(
        context,
        AuditCommand(
            uuid7(),
            AuditCommandType.EVALUATE_DOCUMENT_DELTA,
            scope.audit_process_id,
            5,
            f"audit-process:{scope.audit_process_id}:document-delta-repeat",
            "service:synthetic-audit",
            "audit.document.evaluate",
            uuid7(),
            uuid7(),
            DIGEST,
        ),
        document_delta,
    )
    assert not repeated_evaluation.accepted
    assert repeated_evaluation.outcome_code == "CONCURRENCY_CONFLICT"
    with postgres_environment.audit_engine.begin() as connection:
        set_scope(connection, tenant)
        assert (
            connection.scalar(sa.text("SELECT count(*) FROM workspace.audit_delta_versions")) == 1
        )

    causal_delta = CausalReadinessDelta(
        uuid7(),
        1,
        scope,
        DeltaDenominator(
            uuid7(),
            1,
            ("synthetic-material-batch",),
            ("synthetic-material-batch",),
            scope.rule_set_version_id,
            ("rule-trace:synthetic",),
        ),
        (
            CausalImpactPath(
                uuid7(),
                "material-batch:1",
                None,
                None,
                "work:sheet-pile",
                None,
                None,
                None,
                None,
                None,
                DeltaState.BLOCKED,
                (),
                ("MATERIAL_CERTIFICATE_MISSING",),
                ("id_package", "payment_readiness"),
            ),
        ),
    )
    causal = store.evaluate_causal_delta(
        context,
        AuditCommand(
            uuid7(),
            AuditCommandType.EVALUATE_CAUSAL_DELTA,
            scope.audit_process_id,
            6,
            f"audit-process:{scope.audit_process_id}:causal-delta",
            "service:synthetic-audit",
            "audit.causal.evaluate",
            uuid7(),
            uuid7(),
            DIGEST,
        ),
        causal_delta,
    )
    assert causal.accepted and causal.revision == 7
    package_delta = PackageReadiness(
        uuid7(),
        1,
        scope,
        DeltaDenominator(
            uuid7(),
            1,
            ("synthetic-package",),
            ("support.aosr",),
            scope.rule_set_version_id,
            ("rule-trace:synthetic",),
        ),
        (
            PackageAssessment(
                uuid7(),
                1,
                None,
                "synthetic-section",
                (),
                DeltaState.SATISFIED,
                DeltaState.MISSING,
                DeltaState.MISSING,
                DeltaState.MISSING,
                DeltaState.MISSING,
                ("SIGNATURES_AND_HANDOVER_UNAVAILABLE",),
            ),
        ),
    )
    packaged = store.evaluate_package_readiness(
        context,
        AuditCommand(
            uuid7(),
            AuditCommandType.EVALUATE_PACKAGE_READINESS,
            scope.audit_process_id,
            7,
            f"audit-process:{scope.audit_process_id}:package-delta",
            "service:synthetic-audit",
            "audit.package.evaluate",
            uuid7(),
            uuid7(),
            DIGEST,
        ),
        package_delta,
    )
    assert packaged.accepted and packaged.revision == 8
    with postgres_environment.audit_engine.begin() as connection:
        set_scope(connection, tenant)
        assert (
            connection.scalar(sa.text("SELECT count(*) FROM workspace.audit_delta_versions")) == 3
        )
        assert (
            connection.scalar(sa.text("SELECT count(*) FROM workspace.audit_causal_path_versions"))
            == 1
        )
        assert (
            connection.scalar(
                sa.text("SELECT count(*) FROM workspace.audit_package_delta_memberships")
            )
            == 1
        )

    other = create_tenant(postgres_environment, tenant.organization_id)
    activate(postgres_environment, other)
    with pytest.raises(ValueError, match="not visible"):
        store.apply_command(
            audit_context(other),
            AuditCommand(
                uuid7(),
                AuditCommandType.EVALUATE_DOCUMENT_DELTA,
                scope.audit_process_id,
                revision,
                f"audit-process:{scope.audit_process_id}:cross-workspace",
                "service:synthetic-audit",
                "audit.process.transition",
                uuid7(),
                uuid7(),
                DIGEST,
            ),
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
    migration_head: str, postgres_environment: PostgreSQLEnvironment, repository_root: object
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
                == migration_head
            )
    finally:
        os.environ.pop("ASD_ALLOW_DESTRUCTIVE_DOWNGRADE", None)
        drop_database(cluster, database_name)
        cluster.dispose()
