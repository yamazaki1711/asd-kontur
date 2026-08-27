from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

import pytest
import sqlalchemy as sa
from sqlalchemy.exc import DBAPIError

from asd_kontur.construction_harness.assembly import ConstructionHarnessContextAssembler
from asd_kontur.construction_harness.durability import build_harness_backup_manifest
from asd_kontur.construction_harness.gateway import PostgresConstructionHarnessQueryService
from asd_kontur.construction_harness.models import (
    ConstructionWorkPackage,
    HarnessMemorySnapshot,
    ProjectDefinition,
    RequiredIDDocument,
    RequirementAuthority,
    SourceEvidence,
    WorkRequirementMatrix,
    WorkRequirementRow,
)
from asd_kontur.construction_harness.postgres import (
    ConstructionHarnessProjectionRepository,
    ConstructionHarnessRepository,
)
from asd_kontur.domain import deterministic_uuid
from asd_kontur.knowledge.gateway import GatewayContext, GatewayStatus
from asd_kontur.lifecycle import (
    AdapterHealth,
    PostgresWorkspaceStorageAdapter,
    StorageAdapterDefinition,
)

from .conftest import PostgreSQLEnvironment
from .test_workspace_lifecycle import create_tenant, workspace_context

pytestmark = pytest.mark.postgres
ZERO = "sha256:" + "0" * 64


def _id(value: str) -> UUID:
    return deterministic_uuid(f"integration-construction-harness:{value}")


def _project(organization_id: UUID, workspace_id: UUID) -> ProjectDefinition:
    evidence = SourceEvidence(_id("source"), "pdf:page=7;section=ПЗ", ZERO, _id("evidence"))
    packages = tuple(
        ConstructionWorkPackage(
            _id(f"package:{key}"),
            1,
            workspace_id,
            key,
            "work-taxonomy-v1.0.0",
            key,
            (),
            (),
            (),
            (),
            (evidence,),
        )
        for key in ("earthworks", "reinforced-concrete", "pipeline-installation")
    )
    return ProjectDefinition(
        _id(f"project:{workspace_id}"),
        1,
        organization_id,
        workspace_id,
        "synthetic integration",
        "multi-work",
        (),
        packages,
        (evidence.source_version_id,),
        datetime(2026, 8, 25, tzinfo=UTC),
    )


def _scope(connection: sa.Connection, organization_id: UUID, workspace_id: UUID) -> None:
    connection.execute(
        sa.select(
            sa.func.set_config("asd.organization_id", str(organization_id), True),
            sa.func.set_config("asd.workspace_id", str(workspace_id), True),
        )
    ).one()


def test_unified_harness_schema_role_rls_and_scoped_repository(
    postgres_environment: PostgreSQLEnvironment,
) -> None:
    inspector = sa.inspect(postgres_environment.owner_engine)
    assert {
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
    } <= set(inspector.get_table_names(schema="workspace"))
    tenant_a = create_tenant(postgres_environment)
    tenant_b = create_tenant(postgres_environment, tenant_a.organization_id)
    project_a = _project(tenant_a.organization_id, tenant_a.workspace_id)
    project_b = _project(tenant_b.organization_id, tenant_b.workspace_id)
    ConstructionHarnessRepository(
        postgres_environment.harness_engine, workspace_context(tenant_a)
    ).register_project(project_a)
    ConstructionHarnessRepository(
        postgres_environment.harness_engine, workspace_context(tenant_b)
    ).register_project(project_b)
    matrix = WorkRequirementMatrix(
        _id("matrix-a"),
        1,
        tenant_a.organization_id,
        tenant_a.workspace_id,
        project_a.project_definition_id,
        project_a.version,
        tuple(
            WorkRequirementRow(
                work.work_package_id,
                (),
                (),
                (
                    RequiredIDDocument(
                        _id(f"document:{work.work_type_key}"),
                        f"ID-{work.work_type_key}",
                        1,
                        None,
                        ("practice:verified",),
                        RequirementAuthority.NORMATIVE_GAP,
                    ),
                ),
                ("official_ntd_subset_empty",),
            )
            for work in project_a.work_packages
        ),
        (),
        None,
        datetime(2026, 8, 25, tzinfo=UTC),
    )
    repository_a = ConstructionHarnessRepository(
        postgres_environment.harness_engine, workspace_context(tenant_a)
    )
    repository_a.register_matrix(matrix)
    with pytest.raises(DBAPIError):
        with postgres_environment.harness_engine.begin() as connection:
            _scope(connection, tenant_a.organization_id, tenant_a.workspace_id)
            connection.execute(
                sa.text(
                    "INSERT INTO workspace.customer_regulation_additions "
                    "(organization_id,workspace_id,addition_id,version,matrix_id,matrix_version,"
                    "document_requirement_id,target_authority_status,additional_copies,"
                    "additional_evidence_kinds,source_version_id,source_locator,evidence_link_id,"
                    "created_at) VALUES (:organization,:workspace,:addition,1,:matrix,1,:document,"
                    "'normative_verified',2,'{}'::text[],:source,'regulation:p=2',:evidence,"
                    "CURRENT_TIMESTAMP)"
                ),
                {
                    "organization": tenant_a.organization_id,
                    "workspace": tenant_a.workspace_id,
                    "addition": _id("invalid-customer-addition"),
                    "matrix": matrix.matrix_id,
                    "document": matrix.rows[0].documents[0].document_requirement_id,
                    "source": _id("customer-source"),
                    "evidence": _id("customer-evidence"),
                },
            )
    pack = ConstructionHarnessContextAssembler().assemble(
        project=project_a,
        matrix=matrix,
        memory=HarnessMemorySnapshot(
            (),
            ("practice-unit:verified",),
            (),
            (),
            (),
            (),
            ({"code": "official_ntd_subset_empty"},),
        ),
    )
    repository_a.register_context_pack(pack)
    backup = build_harness_backup_manifest(
        manifest_id=_id("backup-a"),
        project=project_a,
        matrix=matrix,
        context_pack=pack,
        platform_memory_fingerprints=("practice-memory-v1", "ntd-memory-v1"),
        projection_profile_version="harness-exact-v1.0.0",
        created_on=datetime(2026, 8, 25, tzinfo=UTC).date(),
    )
    repository_a.register_backup(backup)
    projection = ConstructionHarnessProjectionRepository(
        postgres_environment.projection_engine, workspace_context(tenant_a)
    )
    first_projection_fingerprint = projection.rebuild(matrix, "harness-exact-v1.0.0")
    projection.delete_rebuildable_plane(matrix)
    second_projection_fingerprint = projection.rebuild(matrix, "harness-exact-v1.0.0")
    assert second_projection_fingerprint == first_projection_fingerprint
    with postgres_environment.harness_engine.begin() as connection:
        _scope(connection, tenant_a.organization_id, tenant_a.workspace_id)
        rows = connection.execute(
            sa.text(
                "SELECT project_definition_id,workspace_id FROM "
                "workspace.project_definition_versions"
            )
        ).all()
    assert rows == [(project_a.project_definition_id, tenant_a.workspace_id)]
    with postgres_environment.harness_engine.begin() as connection:
        _scope(connection, tenant_a.organization_id, tenant_a.workspace_id)
        assert (
            connection.scalar(
                sa.text(
                    "SELECT semantic_fingerprint FROM "
                    "workspace.construction_harness_backup_manifests"
                )
            )
            == backup.semantic_fingerprint
        )
    query = PostgresConstructionHarnessQueryService(postgres_environment.harness_engine)
    response = query.execute(
        "knowledge.get_construction_harness_context",
        {"context_pack_id": str(pack.context_pack_id)},
        GatewayContext(
            "model:qwen",
            "knowledge.get_construction_harness_context.invoke",
            "construction.analysis",
            _id("correlation"),
            tenant_a.organization_id,
            tenant_a.workspace_id,
        ),
    )
    assert response.status is GatewayStatus.KNOWLEDGE_INCOMPLETE
    assert response.result["authority_layers"]["methodological_practice"]
    other_response = query.execute(
        "knowledge.get_construction_harness_context",
        {"context_pack_id": str(pack.context_pack_id)},
        GatewayContext(
            "model:qwen",
            "knowledge.get_construction_harness_context.invoke",
            "construction.analysis",
            _id("other-correlation"),
            tenant_b.organization_id,
            tenant_b.workspace_id,
        ),
    )
    assert other_response.status is GatewayStatus.NO_RESULT
    assert "workspace.project_definition_versions" in PostgresWorkspaceStorageAdapter.TABLES
    adapter = PostgresWorkspaceStorageAdapter(
        postgres_environment.destruction_engine,
        tenant_a.organization_id,
        StorageAdapterDefinition(
            "postgres.workspace",
            "1.8.0",
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
        ),
    )
    with postgres_environment.owner_engine.connect() as connection:
        platform_before = (
            connection.scalar(sa.text("SELECT count(*) FROM platform.practice_guides")),
            connection.scalar(sa.text("SELECT count(*) FROM platform.normative_documents")),
        )
    for item in adapter.inventory(tenant_a.workspace_id):
        adapter.purge_item(
            workspace_id=tenant_a.workspace_id,
            item_id=item.item_id,
            operation_id=_id(f"purge:{item.item_id}"),
        )
    with postgres_environment.owner_engine.connect() as connection:
        assert platform_before == (
            connection.scalar(sa.text("SELECT count(*) FROM platform.practice_guides")),
            connection.scalar(sa.text("SELECT count(*) FROM platform.normative_documents")),
        )
        assert (
            connection.scalar(
                sa.text(
                    "SELECT count(*) FROM workspace.project_definition_versions "
                    "WHERE workspace_id=:workspace"
                ),
                {"workspace": tenant_b.workspace_id},
            )
            == 1
        )
    with postgres_environment.owner_engine.connect() as connection:
        assert (
            connection.scalar(sa.text("SELECT version_num FROM alembic_version"))
            == "0026_support_id_finalize"
        )
        assert (
            connection.scalar(
                sa.text("SELECT rolname FROM pg_roles WHERE rolname='asd_harness_service'")
            )
            == "asd_harness_service"
        )


def test_platform_practice_and_ntd_memory_are_not_workspace_owned(
    postgres_environment: PostgreSQLEnvironment,
) -> None:
    inspector = sa.inspect(postgres_environment.owner_engine)
    practice_columns = {
        item["name"] for item in inspector.get_columns("practice_guides", schema="platform")
    }
    ntd_columns = {
        item["name"] for item in inspector.get_columns("normative_documents", schema="platform")
    }
    assert "workspace_id" not in practice_columns
    assert "workspace_id" not in ntd_columns
    assert "workspace.project_definition_versions" in PostgresWorkspaceStorageAdapter.TABLES
