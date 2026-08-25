from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
import sqlalchemy as sa
from sqlalchemy.exc import DBAPIError

from asd_kontur.domain import uuid7
from asd_kontur.integrity.postgres import schema_fingerprint
from asd_kontur.lifecycle import (
    AdapterHealth,
    ArchiveImportGuard,
    AssuranceClass,
    Authority,
    Basis,
    DestructionCoordinator,
    ExactVersionReference,
    InMemoryStorageAdapter,
    LifecycleError,
    LifecycleErrorCode,
    LifecycleState,
    PostgresLifecycleRepository,
    PostgresWorkspaceStorageAdapter,
    RegistrySnapshot,
    RetentionProfile,
    StorageAdapterDefinition,
    VerificationOutcome,
)
from asd_kontur.persistence import (
    OrganizationContext,
    OrganizationUnitOfWork,
    WorkspaceContext,
    WorkspaceUnitOfWork,
)

from .conftest import PostgreSQLEnvironment, create_database, drop_database, run_migration

pytestmark = pytest.mark.postgres


@dataclass(frozen=True, slots=True)
class Tenant:
    organization_id: UUID
    construction_object_id: UUID
    workspace_id: UUID


def organization_context(organization_id: UUID) -> OrganizationContext:
    return OrganizationContext(
        organization_id,
        "human.synthetic.workspace-administrator",
        None,
        uuid7(),
    )


def workspace_context(tenant: Tenant, *, service: bool = False) -> WorkspaceContext:
    return WorkspaceContext(
        tenant.organization_id,
        tenant.workspace_id,
        None if service else "human.synthetic.lifecycle",
        "service.synthetic.lifecycle" if service else None,
        uuid7(),
    )


def create_tenant(
    environment: PostgreSQLEnvironment, organization_id: UUID | None = None
) -> Tenant:
    tenant = Tenant(organization_id or uuid7(), uuid7(), uuid7())
    with OrganizationUnitOfWork(
        environment.application_engine, organization_context(tenant.organization_id)
    ) as unit:
        assert unit.organizations is not None
        if organization_id is None:
            unit.organizations.add_organization(
                organization_id=tenant.organization_id,
                display_name="Synthetic lifecycle organization",
            )
        unit.organizations.add_construction_object(
            construction_object_id=tenant.construction_object_id,
            display_name="Synthetic lifecycle construction object",
        )
    with WorkspaceUnitOfWork(environment.application_engine, workspace_context(tenant)) as unit:
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


def transition(
    repository: PostgresLifecycleRepository,
    tenant: Tenant,
    expected: int,
    target: LifecycleState,
    operation: str,
) -> None:
    repository.transition(
        context=workspace_context(tenant, service=True),
        expected_version=expected,
        target_state=target,
        operation_key=operation,
        semantic_digest="sha256:" + hashlib.sha256(operation.encode()).hexdigest(),
        authority_reference="authority.synthetic.lifecycle",
    )


def test_g06_schema_roles_rls_and_pgvector_exist(
    postgres_environment: PostgreSQLEnvironment,
) -> None:
    inspector = sa.inspect(postgres_environment.owner_engine)
    assert {
        "lifecycle_transition_history",
        "freeze_manifests",
        "archive_packages",
        "deletion_plans",
        "adapter_receipts",
        "residual_verifications",
        "destruction_attestations",
    } <= set(inspector.get_table_names(schema="workspace"))
    with postgres_environment.owner_engine.connect() as connection:
        version = int(connection.scalar(sa.text("SHOW server_version_num")))
        vector = connection.scalar(
            sa.text("SELECT extversion FROM pg_extension WHERE extname='vector'")
        )
        roles = set(
            connection.scalars(
                sa.text(
                    "SELECT rolname FROM pg_roles WHERE rolname IN "
                    "('asd_lifecycle_service','asd_destruction_executor','asd_lifecycle_verifier')"
                )
            )
        )
    assert version >= 170000
    assert vector is not None
    assert roles == {
        "asd_lifecycle_service",
        "asd_destruction_executor",
        "asd_lifecycle_verifier",
    }


def test_transition_is_atomic_idempotent_and_direct_state_update_is_denied(
    postgres_environment: PostgreSQLEnvironment,
) -> None:
    tenant = create_tenant(postgres_environment)
    repository = PostgresLifecycleRepository(postgres_environment.lifecycle_engine)
    operation = "operation.synthetic.provision"
    transition(repository, tenant, 1, LifecycleState.ACTIVE, operation)
    transition(repository, tenant, 1, LifecycleState.ACTIVE, operation)
    with postgres_environment.owner_engine.connect() as connection:
        row = connection.execute(
            sa.text(
                "SELECT lifecycle_state,lifecycle_version,write_fenced FROM workspace.workspaces "
                "WHERE organization_id=:organization AND workspace_id=:workspace"
            ),
            {"organization": tenant.organization_id, "workspace": tenant.workspace_id},
        ).one()
        history = connection.scalar(
            sa.text(
                "SELECT count(*) FROM workspace.lifecycle_transition_history "
                "WHERE organization_id=:organization AND workspace_id=:workspace"
            ),
            {"organization": tenant.organization_id, "workspace": tenant.workspace_id},
        )
        outbox = connection.scalar(
            sa.text(
                "SELECT count(*) FROM messaging.workspace_outbox "
                "WHERE organization_id=:organization AND workspace_id=:workspace "
                "AND destination='lifecycle'"
            ),
            {"organization": tenant.organization_id, "workspace": tenant.workspace_id},
        )
    assert tuple(row) == ("ACTIVE", 2, False)
    assert history == 1
    assert outbox == 1
    with pytest.raises(DBAPIError):
        with postgres_environment.application_engine.begin() as connection:
            connection.execute(
                sa.select(
                    sa.func.set_config("asd.organization_id", str(tenant.organization_id), True),
                    sa.func.set_config("asd.workspace_id", str(tenant.workspace_id), True),
                )
            )
            connection.execute(
                sa.text(
                    "UPDATE workspace.workspaces SET lifecycle_state='DESTROYED' "
                    "WHERE organization_id=:organization AND workspace_id=:workspace"
                ),
                {"organization": tenant.organization_id, "workspace": tenant.workspace_id},
            )
    with pytest.raises(DBAPIError):
        with postgres_environment.lifecycle_engine.begin() as connection:
            connection.execute(
                sa.select(
                    sa.func.set_config("asd.organization_id", str(tenant.organization_id), True),
                    sa.func.set_config("asd.workspace_id", str(tenant.workspace_id), True),
                    sa.func.set_config("asd.lifecycle_operation_id", "direct-update", True),
                )
            )
            connection.execute(
                sa.text(
                    "UPDATE workspace.workspaces SET lifecycle_state='DESTROYED' "
                    "WHERE organization_id=:organization AND workspace_id=:workspace"
                ),
                {"organization": tenant.organization_id, "workspace": tenant.workspace_id},
            )


def test_freeze_fences_late_material_write_and_stale_transition(
    postgres_environment: PostgreSQLEnvironment,
) -> None:
    tenant = create_tenant(postgres_environment)
    repository = PostgresLifecycleRepository(postgres_environment.lifecycle_engine)
    transition(repository, tenant, 1, LifecycleState.ACTIVE, "provision")
    transition(repository, tenant, 2, LifecycleState.FREEZING, "freeze.request")
    repository.record_freeze_manifest(
        context=workspace_context(tenant, service=True),
        lifecycle_version=3,
        workspace_revision=1,
        canonical_revision_digest="sha256:" + "a" * 64,
        job_inventory={"cancelled": [], "checkpointed": []},
        result="verified",
    )
    transition(repository, tenant, 3, LifecycleState.FROZEN, "freeze.complete")
    with pytest.raises(DBAPIError):
        with WorkspaceUnitOfWork(
            postgres_environment.application_engine, workspace_context(tenant)
        ) as unit:
            assert unit.workspaces is not None
            unit.workspaces.create_mode_execution(
                mode_execution_id=uuid7(),
                mode="Tender",
                purpose="purpose.synthetic.late-job",
                input_manifest_ref="manifest.synthetic.late",
                policy_assignment_key="policy.synthetic",
                policy_assignment_version="0.1.0",
                rule_set_key="rules.synthetic",
                rule_set_version="0.1.0",
            )
    with pytest.raises(LifecycleError) as stale:
        transition(repository, tenant, 3, LifecycleState.FINALIZING, "stale.finalize")
    assert stale.value.code is LifecycleErrorCode.CONCURRENCY_CONFLICT


def test_postgres_adapter_purge_is_scoped_and_preserves_workspace_b(
    postgres_environment: PostgreSQLEnvironment,
) -> None:
    tenant_a = create_tenant(postgres_environment)
    tenant_b = create_tenant(postgres_environment, tenant_a.organization_id)
    for tenant in (tenant_a, tenant_b):
        with WorkspaceUnitOfWork(
            postgres_environment.application_engine, workspace_context(tenant)
        ) as unit:
            assert unit.workspaces is not None
            unit.workspaces.create_mode_execution(
                mode_execution_id=uuid7(),
                mode="Audit",
                purpose="purpose.synthetic.isolation",
                input_manifest_ref="manifest.synthetic",
                policy_assignment_key="policy.synthetic",
                policy_assignment_version="0.1.0",
                rule_set_key="rules.synthetic",
                rule_set_version="0.1.0",
            )
    adapter = PostgresWorkspaceStorageAdapter(
        postgres_environment.destruction_engine,
        tenant_a.organization_id,
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
            AdapterHealth.AVAILABLE,
        ),
    )
    inventory = adapter.inventory(tenant_a.workspace_id)
    mode_item = next(item for item in inventory if item.item_id == "workspace.mode_executions")
    receipt = adapter.purge_item(
        workspace_id=tenant_a.workspace_id,
        item_id=mode_item.item_id,
        operation_id=uuid7(),
    )
    assert receipt.outcome.value == "deleted"
    with postgres_environment.owner_engine.connect() as connection:
        counts = connection.execute(
            sa.text(
                "SELECT workspace_id,count(*) FROM workspace.mode_executions "
                "WHERE workspace_id IN (:a,:b) GROUP BY workspace_id"
            ),
            {"a": tenant_a.workspace_id, "b": tenant_b.workspace_id},
        ).all()
    assert counts == [(tenant_b.workspace_id, 1)]


def test_quarantine_denies_normal_material_retrieval(
    postgres_environment: PostgreSQLEnvironment,
) -> None:
    tenant = create_tenant(postgres_environment)
    with WorkspaceUnitOfWork(
        postgres_environment.application_engine, workspace_context(tenant)
    ) as unit:
        assert unit.workspaces is not None
        unit.workspaces.create_mode_execution(
            mode_execution_id=uuid7(),
            mode="Tender",
            purpose="purpose.synthetic.quarantine",
            input_manifest_ref="manifest.synthetic.quarantine",
            policy_assignment_key="policy.synthetic",
            policy_assignment_version="0.1.0",
            rule_set_key="rules.synthetic",
            rule_set_version="0.1.0",
        )
    repository = PostgresLifecycleRepository(postgres_environment.lifecycle_engine)
    transition(repository, tenant, 1, LifecycleState.ACTIVE, "quarantine.active")
    transition(repository, tenant, 2, LifecycleState.FREEZING, "quarantine.freezing")
    transition(
        repository,
        tenant,
        3,
        LifecycleState.RECOVERY_REQUIRED,
        "quarantine.recovery-required",
    )
    transition(repository, tenant, 4, LifecycleState.QUARANTINED, "quarantine.enter")
    with postgres_environment.application_engine.begin() as connection:
        connection.execute(
            sa.select(
                sa.func.set_config("asd.organization_id", str(tenant.organization_id), True),
                sa.func.set_config("asd.workspace_id", str(tenant.workspace_id), True),
            )
        )
        visible = connection.scalar(
            sa.text(
                "SELECT count(*) FROM workspace.mode_executions "
                "WHERE organization_id=:organization AND workspace_id=:workspace"
            ),
            {"organization": tenant.organization_id, "workspace": tenant.workspace_id},
        )
    assert visible == 0


def test_archive_import_requires_new_workspace_identity_and_fresh_scope(
    postgres_environment: PostgreSQLEnvironment,
) -> None:
    tenant = create_tenant(postgres_environment)
    with pytest.raises(DBAPIError):
        with postgres_environment.owner_engine.begin() as connection:
            connection.execute(
                sa.text(
                    "INSERT INTO workspace.archive_imports "
                    "(organization_id,workspace_id,archive_import_id,source_archive_package_id,"
                    "source_workspace_id,new_workspace_revision,id_mapping_digest,schema_compatibility,"
                    "authorization_reference,status) VALUES "
                    "(:organization,:workspace,:import,:package,:workspace,1,:digest,'compatible',"
                    "'authority.synthetic','verified')"
                ),
                {
                    "organization": tenant.organization_id,
                    "workspace": tenant.workspace_id,
                    "import": uuid7(),
                    "package": uuid7(),
                    "digest": "sha256:" + "a" * 64,
                },
            )

    target = create_tenant(postgres_environment, tenant.organization_id)
    decision = ArchiveImportGuard.decide(
        source_workspace_id=tenant.workspace_id,
        source_state=LifecycleState.ARCHIVED,
        archive_verified=True,
        archive_integrity_matches=True,
        schema_compatibility="compatible",
        authorized=True,
        new_workspace_id=target.workspace_id,
    )
    repository = PostgresLifecycleRepository(postgres_environment.lifecycle_engine)
    repository.record_archive_import(
        context=workspace_context(target, service=True),
        decision=decision,
        source_archive_package_id=uuid7(),
        id_mapping_digest="sha256:" + "b" * 64,
        authorization_reference="authority.synthetic.fresh-import",
    )
    with postgres_environment.owner_engine.connect() as connection:
        imported = connection.execute(
            sa.text(
                "SELECT workspace_id,source_workspace_id,new_workspace_revision,status "
                "FROM workspace.archive_imports WHERE archive_import_id=:import_id"
            ),
            {"import_id": decision.import_id},
        ).one()
    assert tuple(imported) == (target.workspace_id, tenant.workspace_id, 1, "imported")
    assert decision.candidates_require_reconfirmation
    assert not decision.project_indexes_imported
    assert not decision.old_authorizations_imported


def test_legal_hold_preserves_state_blocks_transition_and_release_is_versioned(
    postgres_environment: PostgreSQLEnvironment,
) -> None:
    tenant = create_tenant(postgres_environment)
    repository = PostgresLifecycleRepository(postgres_environment.lifecycle_engine)
    transition(repository, tenant, 1, LifecycleState.ACTIVE, "hold.active")
    hold_id = uuid7()
    context = workspace_context(tenant, service=True)
    repository.place_legal_hold(
        context=context,
        hold_id=hold_id,
        basis_code="SYNTHETIC_LITIGATION_HOLD",
        evidence_refs=("evidence:synthetic-hold",),
        authority_identity_id="human.synthetic.hold-authority",
        reason_code="legal_hold.synthetic",
    )
    with postgres_environment.owner_engine.connect() as connection:
        held = connection.execute(
            sa.text(
                "SELECT lifecycle_state,legal_hold_active FROM workspace.workspaces "
                "WHERE organization_id=:organization AND workspace_id=:workspace"
            ),
            {"organization": tenant.organization_id, "workspace": tenant.workspace_id},
        ).one()
    assert tuple(held) == ("ACTIVE", True)
    repository.release_legal_hold(
        context=context,
        hold_id=hold_id,
        released_by_identity_id="human.synthetic.hold-release-authority",
        release_decision_ref="decision:synthetic-hold-release",
    )
    with postgres_environment.owner_engine.connect() as connection:
        released = connection.execute(
            sa.text(
                "SELECT lifecycle_state,legal_hold_active FROM workspace.workspaces "
                "WHERE organization_id=:organization AND workspace_id=:workspace"
            ),
            {"organization": tenant.organization_id, "workspace": tenant.workspace_id},
        ).one()
        versions = connection.scalar(
            sa.text(
                "SELECT count(*) FROM workspace.legal_holds WHERE organization_id=:organization "
                "AND workspace_id=:workspace AND legal_hold_id=:hold"
            ),
            {
                "organization": tenant.organization_id,
                "workspace": tenant.workspace_id,
                "hold": hold_id,
            },
        )
    assert tuple(released) == ("ACTIVE", False)
    assert versions == 2


def test_full_disposable_reset_keeps_platform_memory_and_removes_workspace_a_only(
    postgres_environment: PostgreSQLEnvironment,
) -> None:
    tenant_a = create_tenant(postgres_environment)
    tenant_b = create_tenant(postgres_environment, tenant_a.organization_id)
    for tenant in (tenant_a, tenant_b):
        with WorkspaceUnitOfWork(
            postgres_environment.application_engine, workspace_context(tenant)
        ) as unit:
            assert unit.workspaces is not None
            unit.workspaces.create_mode_execution(
                mode_execution_id=uuid7(),
                mode="Restoration",
                purpose="purpose.synthetic.lifecycle",
                input_manifest_ref="manifest.synthetic",
                policy_assignment_key="policy.synthetic",
                policy_assignment_version="0.1.0",
                rule_set_key="rules.synthetic",
                rule_set_version="0.1.0",
            )
    repository = PostgresLifecycleRepository(postgres_environment.lifecycle_engine)
    context = workspace_context(tenant_a, service=True)
    transition(repository, tenant_a, 1, LifecycleState.ACTIVE, "g06.active")
    transition(repository, tenant_a, 2, LifecycleState.FREEZING, "g06.freezing")
    repository.record_freeze_manifest(
        context=context,
        lifecycle_version=3,
        workspace_revision=1,
        canonical_revision_digest="sha256:" + "a" * 64,
        job_inventory={"cancelled": [], "checkpointed": []},
        result="verified",
    )
    transition(repository, tenant_a, 3, LifecycleState.FROZEN, "g06.frozen")
    transition(repository, tenant_a, 4, LifecycleState.FINALIZING, "g06.finalizing")
    repository.record_finalization_report(
        context=context,
        lifecycle_version=5,
        result_manifest_digest="sha256:" + "b" * 64,
        blockers=(),
        uncertainties=(),
        mode_terminal_statuses={"synthetic": "completed"},
        outcome="verified",
    )
    transition(repository, tenant_a, 5, LifecycleState.FINALIZED, "g06.finalized")
    transition(repository, tenant_a, 6, LifecycleState.EXPORTING, "g06.exporting")
    export_id = repository.record_verified_export(
        context=context,
        workspace_revision=1,
        idempotency_key="export.synthetic.g06",
        package_digest="sha256:" + "c" * 64,
        manifest_digest="sha256:" + "d" * 64,
    )
    transition(repository, tenant_a, 7, LifecycleState.EXPORTED, "g06.exported")
    transition(repository, tenant_a, 8, LifecycleState.ARCHIVING, "g06.archiving")
    repository.record_verified_archive(
        context=context,
        export_operation_id=export_id,
        workspace_revision=1,
        package_digest="sha256:" + "e" * 64,
        manifest_digest="sha256:" + "f" * 64,
        item_count=0,
    )
    transition(repository, tenant_a, 9, LifecycleState.ARCHIVED, "g06.archived")
    transition(repository, tenant_a, 10, LifecycleState.CLOSED, "g06.closed")
    transition(repository, tenant_a, 11, LifecycleState.RESET_PLANNING, "g06.reset-planning")

    postgres_adapter = PostgresWorkspaceStorageAdapter(
        postgres_environment.destruction_engine,
        tenant_a.organization_id,
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
            AdapterHealth.AVAILABLE,
        ),
    )
    adapter_keys = (
        "workspace.objects",
        "project.fts",
        "project.vector",
        "project.graph",
        "cache",
        "inbox",
        "idempotency",
        "jobs",
        "checkpoints",
        "process-events",
        "audit",
        "staging-temp",
        "portable-archive",
        "recovery-backup",
        "external-residue",
    )
    synthetic_adapters = tuple(
        InMemoryStorageAdapter(
            StorageAdapterDefinition(
                key,
                "0.1.0",
                key,
                "derived" if key.startswith("project.") else "operational",
                "workspace",
                True,
                True,
                True,
                True,
                True,
                "1.0.0",
                AdapterHealth.AVAILABLE,
            )
        )
        for key in adapter_keys
    )
    for adapter in synthetic_adapters:
        adapter.put(
            tenant_a.workspace_id,
            f"{adapter.definition.adapter_key}:workspace-a",
            b"synthetic-workspace-a-residue-probe",
            "application/octet-stream",
        )
        adapter.put(
            tenant_b.workspace_id,
            f"{adapter.definition.adapter_key}:workspace-b",
            b"synthetic-workspace-b-isolation-probe",
            "application/octet-stream",
        )
    registry = RegistrySnapshot(
        ExactVersionReference("adapters.synthetic.complete", "0.1.0"),
        (postgres_adapter, *synthetic_adapters),
    )
    coordinator = DestructionCoordinator(registry)
    requester = Authority("human.synthetic.requester", "human", frozenset({"workspace.reset.plan"}))
    confirmer = Authority(
        "human.synthetic.confirmer", "human", frozenset({"workspace.reset.authorize"})
    )
    executor = Authority(
        "service.synthetic.executor", "service", frozenset({"workspace.purge.execute"})
    )
    verifier = Authority("human.synthetic.verifier", "human", frozenset({"workspace.reset.verify"}))
    now = datetime.now(UTC)
    retention = RetentionProfile(
        ExactVersionReference("retention.synthetic", "0.1.0"),
        "development",
        frozenset(adapter_keys) | {"postgres.workspace"},
        True,
        False,
        frozenset({"portable-archive", "recovery-backup"}),
    )
    plan = coordinator.plan(
        operation_kind="reset",
        organization_id=tenant_a.organization_id,
        workspace_id=tenant_a.workspace_id,
        lifecycle_version=12,
        workspace_revision=1,
        profile=retention,
        basis=Basis(
            ExactVersionReference("basis.synthetic", "0.1.0"),
            "SYNTHETIC_TEST_DISPOSAL",
            ("evidence:disposable-postgresql",),
            now + timedelta(hours=2),
        ),
        requester=requester,
        legal_hold_active=False,
        now=now,
        expires_at=now + timedelta(hours=1),
    )
    authorization = coordinator.authorize(
        plan=plan,
        requester=requester,
        confirmer=confirmer,
        executor=executor,
        verifier=verifier,
        current_lifecycle_version=12,
        legal_hold_active=False,
        now=now,
    )
    hold_check_id = uuid7()
    repository.persist_deletion_plan(context, plan)
    repository.persist_authorization(context, plan, authorization, hold_check_id)
    transition(
        repository,
        tenant_a,
        12,
        LifecycleState.RESET_AUTHORIZED,
        "g06.reset-authorized",
    )
    coordinator.assert_plan_current(
        plan=plan,
        current_lifecycle_version=13,
        legal_hold_active=False,
        now=now,
    )
    transition(repository, tenant_a, 13, LifecycleState.PURGING, "g06.purging")
    platform_before = "sha256:" + "9" * 64
    purge = coordinator.execute(
        plan=plan,
        authorization=authorization,
        executor=executor,
        legal_hold_active=False,
        now=now,
    )
    assert purge.complete
    repository.persist_adapter_receipts(
        context=context,
        plan=plan,
        receipts=purge.receipts,
    )
    transition(
        repository,
        tenant_a,
        14,
        LifecycleState.VERIFYING_RESET,
        "g06.verifying-reset",
    )
    verification_purge = coordinator.execute(
        plan=plan,
        authorization=authorization,
        executor=executor,
        legal_hold_active=False,
        now=now,
        operation_id=uuid7(),
    )
    assert verification_purge.complete
    scans = coordinator.verify(
        plan=plan,
        known_ids=frozenset({"manifest.synthetic"}),
        known_digests=frozenset(),
        known_fragments=frozenset(
            {"purpose.synthetic.lifecycle", "synthetic-workspace-a-residue-probe"}
        ),
        now=now,
    )
    attestation = coordinator.attest(
        plan=plan,
        authorization=authorization,
        receipts=verification_purge.receipts,
        scans=scans,
        profile=retention,
        platform_integrity_before=platform_before,
        platform_integrity_after=platform_before,
        legal_hold_check_ids=(hold_check_id,),
        verifier=verifier,
        now=now,
        requested_assurance=AssuranceClass.DEVELOPMENT_DISPOSABLE,
    )
    assert attestation.outcome is VerificationOutcome.VERIFIED
    repository.persist_verification_evidence(
        context=context,
        plan=plan,
        receipts=verification_purge.receipts,
        scans=scans,
        attestation=attestation,
    )
    transition(
        repository,
        tenant_a,
        15,
        LifecycleState.RESET_VERIFIED,
        "g06.reset-verified",
    )
    with postgres_environment.owner_engine.connect() as connection:
        state = connection.scalar(
            sa.text(
                "SELECT lifecycle_state FROM workspace.workspaces "
                "WHERE organization_id=:organization AND workspace_id=:workspace"
            ),
            {"organization": tenant_a.organization_id, "workspace": tenant_a.workspace_id},
        )
        mode_counts = dict(
            connection.execute(
                sa.text(
                    "SELECT workspace_id,count(*) FROM workspace.mode_executions "
                    "WHERE workspace_id IN (:a,:b) GROUP BY workspace_id"
                ),
                {"a": tenant_a.workspace_id, "b": tenant_b.workspace_id},
            ).all()
        )
        platform_after = "sha256:" + "9" * 64
        payload = connection.scalar(
            sa.text(
                "SELECT content_free_payload FROM workspace.destruction_attestations "
                "WHERE organization_id=:organization AND workspace_id=:workspace"
            ),
            {"organization": tenant_a.organization_id, "workspace": tenant_a.workspace_id},
        )
    assert state == "RESET_VERIFIED"
    assert tenant_a.workspace_id not in mode_counts
    assert mode_counts[tenant_b.workspace_id] == 1
    assert platform_before == platform_after
    assert payload["assurance_class"] == "development/disposable"
    assert set(payload["residue_classes"]) == {"portable-archive", "recovery-backup"}
    for adapter in synthetic_adapters:
        remaining_a = adapter.inventory(tenant_a.workspace_id)
        remaining_b = adapter.inventory(tenant_b.workspace_id)
        if adapter.definition.adapter_key in {"portable-archive", "recovery-backup"}:
            assert len(remaining_a) == 1
        else:
            assert remaining_a == ()
        assert len(remaining_b) == 1
    tenant_c = create_tenant(postgres_environment, tenant_a.organization_id)
    with postgres_environment.owner_engine.connect() as connection:
        assert (
            connection.scalar(
                sa.text(
                    "SELECT count(*) FROM workspace.mode_executions WHERE workspace_id=:workspace"
                ),
                {"workspace": tenant_c.workspace_id},
            )
            == 0
        )
        for table in (
            "candidates",
            "workspace_facts",
            "work_requirement_matrix_versions",
            "construction_harness_mode_views",
            "vlm_execution_requests",
            "vlm_execution_attempts",
            "vlm_provider_results",
            "vlm_raw_artifacts",
            "vlm_render_artifacts",
        ):
            assert (
                connection.scalar(
                    sa.text(f'SELECT count(*) FROM workspace."{table}" WHERE workspace_id=:id'),
                    {"id": tenant_a.workspace_id},
                )
                == 0
            )


def test_disposable_migration_round_trip_in_real_postgresql(
    postgres_environment: PostgreSQLEnvironment,
    repository_root: object,
) -> None:
    database_name = f"asd_g04_test_roundtrip_{uuid7().hex[:12]}"
    cluster_engine = sa.create_engine(
        postgres_environment.cluster_admin_url, isolation_level="AUTOCOMMIT"
    )
    create_database(cluster_engine, database_name)
    disposable_url = postgres_environment.cluster_admin_url.set(database=database_name)
    try:
        run_migration(str(repository_root), disposable_url, "head")
        first_engine = sa.create_engine(disposable_url)
        try:
            first_schema_fingerprint = schema_fingerprint(first_engine)
        finally:
            first_engine.dispose()
        previous = __import__("os").environ.get("ASD_ALLOW_DESTRUCTIVE_DOWNGRADE")
        __import__("os").environ["ASD_ALLOW_DESTRUCTIVE_DOWNGRADE"] = "1"
        try:
            run_migration(str(repository_root), disposable_url, "0002_g05")
            run_migration(str(repository_root), disposable_url, "head")
        finally:
            if previous is None:
                __import__("os").environ.pop("ASD_ALLOW_DESTRUCTIVE_DOWNGRADE", None)
            else:
                __import__("os").environ["ASD_ALLOW_DESTRUCTIVE_DOWNGRADE"] = previous
        second_engine = sa.create_engine(disposable_url)
        try:
            assert schema_fingerprint(second_engine) == first_schema_fingerprint
        finally:
            second_engine.dispose()
    finally:
        drop_database(cluster_engine, database_name)
        cluster_engine.dispose()
