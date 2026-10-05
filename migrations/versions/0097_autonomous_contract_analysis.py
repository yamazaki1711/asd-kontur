"""Add autonomous bounded contract-analysis candidates.

Revision ID: 0097_autonomous_contract_analysis
Revises: 0096_first_fact_fairness
"""

from __future__ import annotations

import os

import sqlalchemy as sa
from alembic import op

revision = "0097_autonomous_contract_analysis"
down_revision = "0096_first_fact_fairness"
branch_labels = None
depends_on = None

_JOB_KIND = "CONTRACT_ANALYSIS"


def _job_constraint_with_contract(include: bool) -> str:
    connection = op.get_bind()
    definition = connection.scalar(
        sa.text(
            "SELECT pg_get_constraintdef(oid) FROM pg_constraint WHERE conrelid="
            "'workspace.durable_jobs'::regclass AND conname='durable_jobs_job_kind_check'"
        )
    )
    if not isinstance(definition, str):
        raise RuntimeError("durable job-kind constraint unavailable")
    if include:
        if _JOB_KIND in definition:
            return definition
        array_end = definition.rfind("]")
        if array_end < 0:
            raise RuntimeError("durable job-kind constraint shape unavailable")
        return definition[:array_end] + f", '{_JOB_KIND}'::text" + definition[array_end:]
    return definition.replace(f", '{_JOB_KIND}'::text", "")


def _replace_fairness(source: str, target: str) -> None:
    connection = op.get_bind()
    definition = connection.scalar(
        sa.text(
            "SELECT pg_get_functiondef("
            "'workspace.claim_next_durable_job(text,integer)'::regprocedure)"
        )
    )
    if not isinstance(definition, str) or source not in definition:
        raise RuntimeError("model-slot fairness definition unavailable")
    connection.execute(sa.text(definition.replace(source, target)))


def upgrade() -> None:
    constraint = _job_constraint_with_contract(True)
    op.execute("ALTER TABLE workspace.durable_jobs DROP CONSTRAINT durable_jobs_job_kind_check")
    op.execute(
        "ALTER TABLE workspace.durable_jobs ADD CONSTRAINT durable_jobs_job_kind_check "
        + constraint
    )
    op.execute(
        """
        CREATE TABLE workspace.contract_analysis_results (
          organization_id uuid NOT NULL,
          workspace_id uuid NOT NULL,
          job_id uuid NOT NULL,
          source_version_id uuid NOT NULL,
          profile_version text NOT NULL CHECK (profile_version='qwen-contract-analysis-v1'),
          batch_ordinal integer NOT NULL CHECK (batch_ordinal>=1),
          source_locator_ids uuid[] NOT NULL CHECK (cardinality(source_locator_ids)>0),
          input_digest text NOT NULL CHECK (input_digest ~ '^sha256:[a-f0-9]{64}$'),
          result_manifest jsonb NOT NULL,
          result_digest text NOT NULL CHECK (result_digest ~ '^sha256:[a-f0-9]{64}$'),
          model_identity text NOT NULL,
          recorded_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
          PRIMARY KEY (organization_id,workspace_id,job_id),
          FOREIGN KEY (organization_id,workspace_id,job_id)
            REFERENCES workspace.durable_jobs(organization_id,workspace_id,job_id) ON DELETE RESTRICT
        )
        """
    )
    op.execute(
        "CREATE INDEX contract_analysis_results_source_idx ON "
        "workspace.contract_analysis_results "
        "(organization_id,workspace_id,source_version_id,batch_ordinal,recorded_at)"
    )
    op.execute("ALTER TABLE workspace.contract_analysis_results ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE workspace.contract_analysis_results FORCE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY contract_analysis_results_scope ON workspace.contract_analysis_results "
        "USING (organization_id=NULLIF(current_setting('asd.organization_id',true),'')::uuid "
        "AND workspace_id=NULLIF(current_setting('asd.workspace_id',true),'')::uuid) WITH CHECK "
        "(organization_id=NULLIF(current_setting('asd.organization_id',true),'')::uuid AND "
        "workspace_id=NULLIF(current_setting('asd.workspace_id',true),'')::uuid)"
    )
    op.execute("GRANT SELECT ON workspace.contract_analysis_results TO asd_app")
    op.execute("GRANT SELECT,INSERT ON workspace.contract_analysis_results TO asd_document_worker")
    op.execute(
        "GRANT SELECT,DELETE ON workspace.contract_analysis_results TO asd_destruction_executor"
    )
    op.execute(
        "CREATE TRIGGER contract_analysis_results_immutable BEFORE UPDATE OR DELETE ON "
        "workspace.contract_analysis_results FOR EACH ROW EXECUTE FUNCTION "
        "application.reject_spine_mutation_except_destruction()"
    )
    _replace_fairness(
        "'PROJECT_STRUCTURE_RECONCILIATION','PROJECT_WORK_RECONCILIATION'",
        "'PROJECT_STRUCTURE_RECONCILIATION','PROJECT_WORK_RECONCILIATION','CONTRACT_ANALYSIS'",
    )


def downgrade() -> None:
    if os.environ.get("ASD_ALLOW_DESTRUCTIVE_DOWNGRADE") != "1":
        raise RuntimeError("Contract-analysis downgrade requires a disposable database")
    _replace_fairness(
        "'PROJECT_STRUCTURE_RECONCILIATION','PROJECT_WORK_RECONCILIATION','CONTRACT_ANALYSIS'",
        "'PROJECT_STRUCTURE_RECONCILIATION','PROJECT_WORK_RECONCILIATION'",
    )
    op.execute("DROP TABLE workspace.contract_analysis_results")
    constraint = _job_constraint_with_contract(False)
    op.execute("ALTER TABLE workspace.durable_jobs DROP CONSTRAINT durable_jobs_job_kind_check")
    op.execute(
        "ALTER TABLE workspace.durable_jobs ADD CONSTRAINT durable_jobs_job_kind_check "
        + constraint
    )
