from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest
import sqlalchemy as sa
from sqlalchemy.engine import make_url

from .conftest import create_database, drop_database, run_migration

pytestmark = pytest.mark.postgres

SPINE_WORKSPACE_TABLES = (
    "contract_analysis_results",
    "document_pages",
    "document_processing_states",
    "document_records",
    "document_version_activation_decisions",
    "document_versions",
    "durable_job_attempts",
    "durable_job_dependencies",
    "durable_jobs",
    "intake_manifest_items",
    "intake_manifests",
    "job_cancellations",
    "job_leases",
    "job_progress_events",
    "job_terminal_receipts",
    "pilot_export_versions",
    "pilot_mode_result_versions",
    "pilot_result_item_decisions",
    "project_work_reconciliation_results",
)


def _schema_fingerprint(engine: sa.Engine) -> str:
    with engine.connect() as connection:
        columns = connection.execute(
            sa.text(
                "SELECT table_schema,table_name,column_name,ordinal_position,data_type,is_nullable,"
                "COALESCE(column_default,'') FROM information_schema.columns "
                "WHERE table_schema='application' OR "
                "(table_schema='workspace' AND table_name=ANY(:tables)) "
                "ORDER BY table_schema,table_name,ordinal_position"
            ),
            {"tables": list(SPINE_WORKSPACE_TABLES)},
        ).all()
        constraints = connection.execute(
            sa.text(
                "SELECT n.nspname,c.relname,con.conname,pg_get_constraintdef(con.oid,true) "
                "FROM pg_constraint con JOIN pg_class c ON c.oid=con.conrelid "
                "JOIN pg_namespace n ON n.oid=c.relnamespace "
                "WHERE n.nspname='application' OR "
                "(n.nspname='workspace' AND c.relname=ANY(:tables)) "
                "ORDER BY n.nspname,c.relname,con.conname"
            ),
            {"tables": list(SPINE_WORKSPACE_TABLES)},
        ).all()
        indexes = connection.execute(
            sa.text(
                "SELECT schemaname,tablename,indexname,indexdef FROM pg_indexes "
                "WHERE schemaname='application' OR "
                "(schemaname='workspace' AND tablename=ANY(:tables)) "
                "ORDER BY schemaname,tablename,indexname"
            ),
            {"tables": list(SPINE_WORKSPACE_TABLES)},
        ).all()
        policies = connection.execute(
            sa.text(
                "SELECT schemaname,tablename,policyname,roles,cmd,qual,with_check FROM pg_policies "
                "WHERE schemaname='application' OR "
                "(schemaname='workspace' AND tablename=ANY(:tables)) "
                "ORDER BY schemaname,tablename,policyname"
            ),
            {"tables": list(SPINE_WORKSPACE_TABLES)},
        ).all()
        triggers = connection.execute(
            sa.text(
                "SELECT n.nspname,c.relname,t.tgname,pg_get_triggerdef(t.oid,true) "
                "FROM pg_trigger t JOIN pg_class c ON c.oid=t.tgrelid "
                "JOIN pg_namespace n ON n.oid=c.relnamespace WHERE NOT t.tgisinternal AND "
                "(n.nspname='application' OR (n.nspname='workspace' AND c.relname=ANY(:tables))) "
                "ORDER BY n.nspname,c.relname,t.tgname"
            ),
            {"tables": list(SPINE_WORKSPACE_TABLES)},
        ).all()
    payload = {
        "columns": [tuple(row) for row in columns],
        "constraints": [tuple(row) for row in constraints],
        "indexes": [tuple(row) for row in indexes],
        "policies": [tuple(row) for row in policies],
        "triggers": [tuple(row) for row in triggers],
    }
    encoded = json.dumps(payload, default=str, separators=(",", ":"), sort_keys=True).encode()
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def test_product_spine_disposable_downgrade_upgrade_is_reproducible(
    repository_root: Path,
    migration_head: str,
) -> None:
    explicit_url = os.environ.get("ASD_TEST_DATABASE_URL")
    if not explicit_url:
        pytest.fail("ASD_TEST_DATABASE_URL is required for the full migration gate")
    base_url = make_url(explicit_url)
    database_name = f"asd_g04_test_spine_roundtrip_{os.getpid()}"
    cluster_url = base_url.set(database="postgres")
    cluster_engine = sa.create_engine(cluster_url, isolation_level="AUTOCOMMIT")
    create_database(cluster_engine, database_name)
    database_url = base_url.set(database=database_name)
    database_engine = sa.create_engine(database_url)
    try:
        run_migration(str(repository_root), database_url, "head")
        before = _schema_fingerprint(database_engine)
        prior = os.environ.get("ASD_ALLOW_DESTRUCTIVE_DOWNGRADE")
        os.environ["ASD_ALLOW_DESTRUCTIVE_DOWNGRADE"] = "1"
        try:
            # Reproduce an existing pre-0046 installation with Alembic's original
            # varchar(32), then verify that upgrading preserves the published ID.
            run_migration(str(repository_root), database_url, "0045_bounded_dep_recovery")
            with database_engine.begin() as connection:
                connection.execute(
                    sa.text("ALTER TABLE alembic_version ALTER COLUMN version_num TYPE varchar(32)")
                )
            run_migration(str(repository_root), database_url, "head")
            with database_engine.connect() as connection:
                assert (
                    connection.scalar(sa.text("SELECT version_num FROM alembic_version"))
                    == migration_head
                )
                claim_definition = str(
                    connection.scalar(
                        sa.text(
                            "SELECT pg_get_functiondef("
                            "'workspace.claim_next_durable_job(text,integer)'::regprocedure)"
                        )
                    )
                )
                contract_priority = claim_definition.index(
                    "CASE WHEN j.job_kind IN "
                    "('CONTRACT_ANALYSIS','CONTRACT_REFERENCE_REVIEW') THEN 3"
                )
                primary_facts_priority = claim_definition.index(
                    "EXISTS (\n                 SELECT 1\n"
                    "                   FROM workspace.document_versions active_version"
                )
                assert contract_priority < primary_facts_priority
                assert primary_facts_priority < claim_definition.index(
                    "SELECT max(served.started_at)"
                )
                assert "PROJECT_DEFINITION_EXTRACTION" in claim_definition
                assert "count(*) FILTER" not in claim_definition
                assert "completed_version" in claim_definition
                assert "incremental_source_job_id" not in claim_definition
                fairness_start = claim_definition.index("SELECT max(served.started_at)")
                fairness_end = claim_definition.index("),'-infinity'::timestamptz)")
                fairness_definition = claim_definition[fairness_start:fairness_end]
                assert "PROJECT_WORK_RECONCILIATION" in fairness_definition
                assert "CONTRACT_ANALYSIS" in fairness_definition
                assert "DOCUMENT_HASH" not in fairness_definition
                contract_profile_constraint = str(
                    connection.scalar(
                        sa.text(
                            "SELECT pg_get_constraintdef(oid) FROM pg_constraint "
                            "WHERE conrelid='workspace.contract_analysis_results'::regclass "
                            "AND conname='contract_analysis_results_profile_version_check'"
                        )
                    )
                )
                assert "qwen-contract-analysis-v1" in contract_profile_constraint
                assert "qwen-contract-analysis-v2" in contract_profile_constraint
                assert "qwen-contract-analysis-v3" in contract_profile_constraint
                assert "qwen-contract-analysis-v4" in contract_profile_constraint
                assert "qwen-contract-analysis-v5" in contract_profile_constraint
                assert "qwen-contract-analysis-v6" in contract_profile_constraint
                assert "qwen-contract-analysis-v7" in contract_profile_constraint
                assert "qwen-contract-analysis-v8" in contract_profile_constraint
                assert "qwen-contract-analysis-v9" in contract_profile_constraint
                assert "qwen-contract-analysis-v10" in contract_profile_constraint
                work_profile_constraint = str(
                    connection.scalar(
                        sa.text(
                            "SELECT pg_get_constraintdef(oid) FROM pg_constraint "
                            "WHERE conrelid="
                            "'workspace.project_work_reconciliation_results'::regclass "
                            "AND conname="
                            "'project_work_reconciliation_results_profile_version_check'"
                        )
                    )
                )
                assert "qwen-project-work-reconciliation-v20" in work_profile_constraint
                assert "qwen-project-work-reconciliation-v21" in work_profile_constraint
                assert "qwen-project-work-reconciliation-v22" in work_profile_constraint
                assert "qwen-project-work-reconciliation-v23" in work_profile_constraint
                assert "qwen-project-work-reconciliation-v24" in work_profile_constraint
                assert "qwen-project-work-reconciliation-v25" in work_profile_constraint
                assert "qwen-project-work-reconciliation-v32" in work_profile_constraint
                assert "qwen-project-work-reconciliation-v33" in work_profile_constraint
                assert "qwen-project-work-reconciliation-v36" in work_profile_constraint
                assert "qwen-project-work-reconciliation-v37" in work_profile_constraint
                assert "qwen-project-work-reconciliation-v38" in work_profile_constraint
                assert "qwen-project-work-reconciliation-v39" in work_profile_constraint
                assert "qwen-project-work-reconciliation-v40" in work_profile_constraint
                expected_claim_indexes = {
                    "ix_durable_jobs_successor_lineage",
                    "ix_durable_jobs_workspace_model_service",
                    "ix_project_stage_source_terminal",
                    "ix_assistant_turns_workspace_active",
                    "ix_durable_jobs_active_project_recency",
                }
                actual_claim_indexes = set(
                    connection.scalars(
                        sa.text(
                            "SELECT indexname FROM pg_indexes WHERE schemaname='workspace' "
                            "AND indexname=ANY(:indexes)"
                        ),
                        {"indexes": sorted(expected_claim_indexes)},
                    )
                )
                assert actual_claim_indexes == expected_claim_indexes

            # 0045 must restore the 0044 wrapper AND retain its v1 implementation.
            run_migration(str(repository_root), database_url, "0044_dep_recovery_idempotency")
            with database_engine.connect() as connection:
                assert (
                    connection.scalar(
                        sa.text("SELECT workspace.recover_dependency_terminal_failures_v1()")
                    )
                    == 0
                )
                assert (
                    connection.scalar(
                        sa.text("SELECT workspace.recover_dependency_terminal_failures()")
                    )
                    == 0
                )
            run_migration(str(repository_root), database_url, "0041_engineering_v4_manifest")
            with database_engine.connect() as connection:
                definition = connection.scalar(
                    sa.text(
                        "SELECT pg_get_functiondef("
                        "'workspace.claim_next_durable_job(text,integer)'::regprocedure)"
                    )
                )
                assert "dependency_success_satisfied" not in str(definition)
                assert (
                    connection.execute(
                        sa.text(
                            "SELECT * FROM workspace.claim_next_durable_job('migration-test', 5)"
                        )
                    ).all()
                    == []
                )
            run_migration(str(repository_root), database_url, "0018_product_spine")
        finally:
            if prior is None:
                os.environ.pop("ASD_ALLOW_DESTRUCTIVE_DOWNGRADE", None)
            else:
                os.environ["ASD_ALLOW_DESTRUCTIVE_DOWNGRADE"] = prior
        with database_engine.connect() as connection:
            assert (
                connection.scalar(sa.text("SELECT to_regclass('workspace.durable_jobs')"))
                is not None
            )
            assert (
                connection.scalar(
                    sa.text("SELECT to_regclass('platform.practice_intelligence_identities')")
                )
                is None
            )
        run_migration(str(repository_root), database_url, "head")
        after = _schema_fingerprint(database_engine)
        assert after == before
    finally:
        database_engine.dispose()
        drop_database(cluster_engine, database_name)
        cluster_engine.dispose()
