from __future__ import annotations

import hashlib
import os
from uuid import UUID

import pytest
import sqlalchemy as sa
from sqlalchemy.exc import DBAPIError

from asd_kontur.domain import uuid7
from asd_kontur.lifecycle import (
    LifecycleState,
    PostgresLifecycleRepository,
    PostgresWorkspaceStorageAdapter,
    StorageAdapterDefinition,
)

from .conftest import PostgreSQLEnvironment, create_database, drop_database, run_migration
from .test_workspace_lifecycle import Tenant, create_tenant, transition

pytestmark = pytest.mark.postgres
DIGEST = "sha256:" + "a" * 64


def _scope(connection: sa.Connection, tenant: Tenant) -> None:
    connection.execute(
        sa.select(
            sa.func.set_config("asd.organization_id", str(tenant.organization_id), True),
            sa.func.set_config("asd.workspace_id", str(tenant.workspace_id), True),
        )
    )


def _seed_source(environment: PostgreSQLEnvironment, tenant: Tenant) -> tuple[UUID, UUID]:
    source = uuid7()
    locator = uuid7()
    object_id = uuid7()
    receipt = uuid7()
    artifact = uuid7()
    attempt = uuid7()
    with environment.owner_engine.begin() as connection:
        connection.execute(
            sa.text(
                "INSERT INTO workspace.objects (organization_id,workspace_id,object_id,object_version,object_class,content_digest,size_bytes,media_type,storage_adapter_key,storage_receipt_ref,access_capability_ref,classification,retention_class,created_by_identity_id,correlation_id) VALUES (:o,:w,:object,1,'source',:digest,9,'application/pdf','synthetic','receipt','capability','synthetic','workspace.source','human.synthetic',:correlation)"
            ),
            {
                "o": tenant.organization_id,
                "w": tenant.workspace_id,
                "object": object_id,
                "digest": DIGEST,
                "correlation": uuid7(),
            },
        )
        connection.execute(
            sa.text(
                "INSERT INTO workspace.source_artifacts (organization_id,workspace_id,source_artifact_id,source_kind,title,status,retention_class,created_by_identity_id,correlation_id) VALUES (:o,:w,:artifact,'rd','Synthetic source','active','workspace.source','human.synthetic',:correlation)"
            ),
            {
                "o": tenant.organization_id,
                "w": tenant.workspace_id,
                "artifact": artifact,
                "correlation": uuid7(),
            },
        )
        connection.execute(
            sa.text(
                "INSERT INTO workspace.source_object_receipts (organization_id,workspace_id,object_receipt_id,object_id,object_version,adapter_key,operation_id,status,observed_digest,observed_size_bytes,residue_state) VALUES (:o,:w,:receipt,:object,1,'synthetic','operation','verified',:digest,9,'none')"
            ),
            {
                "o": tenant.organization_id,
                "w": tenant.workspace_id,
                "receipt": receipt,
                "object": object_id,
                "digest": DIGEST,
            },
        )
        connection.execute(
            sa.text(
                "INSERT INTO workspace.acquisition_attempts (organization_id,workspace_id,acquisition_attempt_id,source_artifact_id,acquisition_method,external_locator,requested_at,retrieved_at,status,observed_content_digest,object_receipt_id,correlation_id) VALUES (:o,:w,:attempt,:artifact,'synthetic','urn:synthetic',CURRENT_TIMESTAMP,CURRENT_TIMESTAMP,'accepted',:digest,:receipt,:correlation)"
            ),
            {
                "o": tenant.organization_id,
                "w": tenant.workspace_id,
                "attempt": attempt,
                "artifact": artifact,
                "digest": DIGEST,
                "receipt": receipt,
                "correlation": uuid7(),
            },
        )
        connection.execute(
            sa.text(
                "INSERT INTO workspace.source_versions (organization_id,workspace_id,source_version_id,source_artifact_id,version_ordinal,external_version_label,object_id,object_receipt_id,acquisition_attempt_id,content_digest,semantic_metadata_digest,acquisition_method,retrieved_at,admission_status,admitted_by_identity_id,retention_class) VALUES (:o,:w,:source,:artifact,1,'synthetic-v1',:object,:receipt,:attempt,:digest,:digest,'synthetic',CURRENT_TIMESTAMP,'accepted','human.synthetic','workspace.source')"
            ),
            {
                "o": tenant.organization_id,
                "w": tenant.workspace_id,
                "source": source,
                "artifact": artifact,
                "object": object_id,
                "receipt": receipt,
                "attempt": attempt,
                "digest": DIGEST,
            },
        )
        connection.execute(
            sa.text(
                "INSERT INTO workspace.source_locators (organization_id,workspace_id,source_locator_id,source_version_id,locator_kind,locator_key,locator_value) VALUES (:o,:w,:locator,:source,'page','page:1',CAST(:locator_value AS jsonb))"
            ),
            {
                "o": tenant.organization_id,
                "w": tenant.workspace_id,
                "locator": locator,
                "source": source,
                "locator_value": '{"page":1}',
            },
        )
    return source, locator


def _seed_profile(environment: PostgreSQLEnvironment) -> tuple[UUID, str]:
    provider = uuid7()
    profile = uuid7()
    version = "1.0.0"
    with environment.owner_engine.begin() as connection:
        connection.execute(
            sa.text(
                "INSERT INTO platform.vlm_provider_versions (provider_id,version,provider_key,provider_kind,network_egress,status,capabilities_digest,owner_identity_id,effective_from,digest) VALUES (:id,:version,:key,'synthetic',false,'evaluation',:digest,'human.synthetic',CURRENT_TIMESTAMP,:digest) ON CONFLICT DO NOTHING"
            ),
            {"id": provider, "version": version, "key": f"provider.{provider}", "digest": DIGEST},
        )
        connection.execute(
            sa.text(
                "INSERT INTO platform.vlm_execution_profile_versions (execution_profile_id,version,profile_key,provider_id,provider_version,model_identity,model_revision,execution_format,quantization,runtime_version,prompt_version,output_schema_version,preprocessing_version,rendering_version,verification_policy_version,heavy_resource_class,status,digest) VALUES (:profile,:version,:key,:provider,:version,'Qwen3.8-27B','synthetic-revision','synthetic','8bit','synthetic','1.0.0','0.1.0','1.0.0','1.0.0','1.0.0','heavy.metal','evaluation',:digest)"
            ),
            {
                "profile": profile,
                "version": version,
                "key": f"profile.{profile}",
                "provider": provider,
                "digest": DIGEST,
            },
        )
    return profile, version


def _insert_request(
    connection: sa.Connection,
    tenant: Tenant,
    source: UUID,
    locator: UUID,
    profile: UUID,
    *,
    request_id: UUID | None = None,
) -> UUID:
    result = request_id or uuid7()
    connection.execute(
        sa.text(
            "INSERT INTO workspace.vlm_execution_requests (organization_id,workspace_id,request_id,source_version_id,purpose,purpose_version,classification,authorized_locator_ids,route,execution_profile_id,execution_profile_version,rule_set_version,authorization_decision_id,routing_policy_version,budget_version,idempotency_key,correlation_id,causation_id,source_digest,payload_digest,request_digest,retention_class) VALUES (:o,:w,:request,:source,'synthetic.extract','1.0.0','synthetic',ARRAY[:locator]::uuid[],'local_vlm',:profile,'1.0.0','1.0.0',:authorization,'1.0.0','1.0.0',:key,:correlation,:causation,:digest,:digest,:request_digest,'workspace.vlm')"
        ),
        {
            "o": tenant.organization_id,
            "w": tenant.workspace_id,
            "request": result,
            "source": source,
            "locator": locator,
            "profile": profile,
            "authorization": uuid7(),
            "key": str(result),
            "correlation": uuid7(),
            "causation": uuid7(),
            "digest": DIGEST,
            "request_digest": "sha256:" + hashlib.sha256(str(result).encode()).hexdigest(),
        },
    )
    return result


def test_g07_schema_roles_rls_and_migration_chain(
    postgres_environment: PostgreSQLEnvironment,
) -> None:
    inspector = sa.inspect(postgres_environment.owner_engine)
    assert {
        "vlm_execution_requests",
        "candidate_versions",
        "vlm_render_artifacts",
        "vlm_batches",
        "vlm_raw_artifacts",
    } <= set(inspector.get_table_names(schema="workspace"))
    with postgres_environment.owner_engine.connect() as connection:
        assert (
            connection.scalar(
                sa.text("SELECT rolname FROM pg_roles WHERE rolname='asd_harness_service'")
            )
            == "asd_harness_service"
        )
        assert connection.scalar(sa.text("SELECT version_num FROM alembic_version")) == "0009_kg_id"


def test_harness_rls_default_deny_and_workspace_isolation(
    postgres_environment: PostgreSQLEnvironment,
) -> None:
    tenant_a = create_tenant(postgres_environment)
    tenant_b = create_tenant(postgres_environment, tenant_a.organization_id)
    transition(
        PostgresLifecycleRepository(postgres_environment.lifecycle_engine),
        tenant_a,
        1,
        LifecycleState.ACTIVE,
        "g07-a-active",
    )
    transition(
        PostgresLifecycleRepository(postgres_environment.lifecycle_engine),
        tenant_b,
        1,
        LifecycleState.ACTIVE,
        "g07-b-active",
    )
    source_a, locator_a = _seed_source(postgres_environment, tenant_a)
    profile, _ = _seed_profile(postgres_environment)
    with postgres_environment.harness_engine.begin() as connection:
        _scope(connection, tenant_a)
        _insert_request(connection, tenant_a, source_a, locator_a, profile)
    with postgres_environment.harness_engine.connect() as connection:
        assert (
            connection.scalar(sa.text("SELECT count(*) FROM workspace.vlm_execution_requests")) == 0
        )
    with postgres_environment.harness_engine.begin() as connection:
        _scope(connection, tenant_b)
        assert (
            connection.scalar(sa.text("SELECT count(*) FROM workspace.vlm_execution_requests")) == 0
        )
        with pytest.raises(DBAPIError):
            _insert_request(connection, tenant_b, source_a, locator_a, profile)


def test_attempts_results_candidates_are_immutable_and_fenced(
    postgres_environment: PostgreSQLEnvironment,
) -> None:
    tenant = create_tenant(postgres_environment)
    lifecycle = PostgresLifecycleRepository(postgres_environment.lifecycle_engine)
    transition(lifecycle, tenant, 1, LifecycleState.ACTIVE, "g07-active")
    source, locator = _seed_source(postgres_environment, tenant)
    profile, _ = _seed_profile(postgres_environment)
    attempt = uuid7()
    candidate = uuid7()
    with postgres_environment.harness_engine.begin() as connection:
        _scope(connection, tenant)
        request_id = _insert_request(connection, tenant, source, locator, profile)
        connection.execute(
            sa.text(
                "INSERT INTO workspace.vlm_execution_attempts (organization_id,workspace_id,attempt_id,request_id,attempt_kind,status,expected_source_digest,started_at) VALUES (:o,:w,:attempt,:request,'initial','completed',:digest,CURRENT_TIMESTAMP)"
            ),
            {
                "o": tenant.organization_id,
                "w": tenant.workspace_id,
                "attempt": attempt,
                "request": request_id,
                "digest": DIGEST,
            },
        )
        connection.execute(
            sa.text(
                "INSERT INTO workspace.candidates (organization_id,workspace_id,candidate_id,purpose,source_version_id,retention_class,created_at) VALUES (:o,:w,:candidate,'synthetic.extract',:source,'workspace.vlm',CURRENT_TIMESTAMP)"
            ),
            {
                "o": tenant.organization_id,
                "w": tenant.workspace_id,
                "candidate": candidate,
                "source": source,
            },
        )
        connection.execute(
            sa.text(
                "INSERT INTO workspace.candidate_versions (organization_id,workspace_id,candidate_id,candidate_version,attempt_id,origin,status,output_schema_version,digest,created_at) VALUES (:o,:w,:candidate,1,:attempt,'vlm','unverified','0.1.0',:digest,CURRENT_TIMESTAMP)"
            ),
            {
                "o": tenant.organization_id,
                "w": tenant.workspace_id,
                "candidate": candidate,
                "attempt": attempt,
                "digest": DIGEST,
            },
        )
    with pytest.raises(DBAPIError):
        with postgres_environment.harness_engine.begin() as connection:
            _scope(connection, tenant)
            connection.execute(
                sa.text(
                    "UPDATE workspace.candidate_versions SET status='validated_candidate' WHERE organization_id=:o AND workspace_id=:w AND candidate_id=:candidate"
                ),
                {"o": tenant.organization_id, "w": tenant.workspace_id, "candidate": candidate},
            )
    transition(lifecycle, tenant, 2, LifecycleState.FREEZING, "g07-freeze")
    with pytest.raises(DBAPIError):
        with postgres_environment.harness_engine.begin() as connection:
            _scope(connection, tenant)
            connection.execute(
                sa.text(
                    "INSERT INTO workspace.vlm_raw_artifacts (organization_id,workspace_id,raw_artifact_id,artifact_kind,content_digest,classification,retention_class,storage_policy,created_at) VALUES (:o,:w,:id,'provider_response',:digest,'synthetic','workspace.vlm','no_raw_storage',CURRENT_TIMESTAMP)"
                ),
                {
                    "o": tenant.organization_id,
                    "w": tenant.workspace_id,
                    "id": uuid7(),
                    "digest": DIGEST,
                },
            )


def test_reset_adapter_purges_harness_data_but_platform_profile_survives(
    postgres_environment: PostgreSQLEnvironment,
) -> None:
    tenant = create_tenant(postgres_environment)
    transition(
        PostgresLifecycleRepository(postgres_environment.lifecycle_engine),
        tenant,
        1,
        LifecycleState.ACTIVE,
        "g07-reset-active",
    )
    profile, _ = _seed_profile(postgres_environment)
    with postgres_environment.owner_engine.begin() as connection:
        connection.execute(
            sa.text(
                "INSERT INTO workspace.vlm_raw_artifacts (organization_id,workspace_id,raw_artifact_id,artifact_kind,content_digest,classification,retention_class,storage_policy,created_at) VALUES (:o,:w,:id,'cache',:digest,'synthetic','workspace.vlm','no_raw_storage',CURRENT_TIMESTAMP)"
            ),
            {
                "o": tenant.organization_id,
                "w": tenant.workspace_id,
                "id": uuid7(),
                "digest": DIGEST,
            },
        )
    definition = StorageAdapterDefinition(
        "postgres.workspace",
        "1.0.0",
        "canonical",
        "authoritative",
        "workspace",
        True,
        True,
        True,
        True,
        False,
        "1.0.0",
    )
    adapter = PostgresWorkspaceStorageAdapter(
        postgres_environment.destruction_engine, tenant.organization_id, definition
    )
    receipt = adapter.purge_item(
        workspace_id=tenant.workspace_id,
        item_id="workspace.vlm_raw_artifacts",
        operation_id=uuid7(),
    )
    assert receipt.after_count == 0
    with postgres_environment.owner_engine.connect() as connection:
        assert (
            connection.scalar(
                sa.text(
                    "SELECT count(*) FROM platform.vlm_execution_profile_versions WHERE execution_profile_id=:profile"
                ),
                {"profile": profile},
            )
            == 1
        )


def test_disposable_head_to_0003_to_head(
    postgres_environment: PostgreSQLEnvironment, repository_root: str
) -> None:
    database_name = f"asd_g04_test_g07_roundtrip_{os.getpid()}"
    cluster = sa.create_engine(postgres_environment.cluster_admin_url, isolation_level="AUTOCOMMIT")
    create_database(cluster, database_name)
    database_url = postgres_environment.cluster_admin_url.set(database=database_name)
    try:
        run_migration(repository_root, database_url, "head")
        os.environ["ASD_ALLOW_DESTRUCTIVE_DOWNGRADE"] = "1"
        run_migration(repository_root, database_url, "0003_g06")
        run_migration(repository_root, database_url, "head")
        with sa.create_engine(database_url).connect() as connection:
            assert (
                connection.scalar(sa.text("SELECT version_num FROM alembic_version"))
                == "0009_kg_id"
            )
    finally:
        os.environ.pop("ASD_ALLOW_DESTRUCTIVE_DOWNGRADE", None)
        drop_database(cluster, database_name)
        cluster.dispose()
