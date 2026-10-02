"""Enable contract v3 results and bound durable-job claim lookups.

Revision ID: 0098_contract_v3_claim_perf
Revises: 0097_autonomous_contract_analysis
"""

from __future__ import annotations

import os

from alembic import op

revision = "0098_contract_v3_claim_perf"
down_revision = "0097_autonomous_contract_analysis"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Keep accepted contract history while enabling v3 and indexed queue claims."""

    op.execute(
        "ALTER TABLE workspace.contract_analysis_results "
        "DROP CONSTRAINT contract_analysis_results_profile_version_check"
    )
    op.execute(
        "ALTER TABLE workspace.contract_analysis_results ADD CONSTRAINT "
        "contract_analysis_results_profile_version_check CHECK (profile_version IN ("
        "'qwen-contract-analysis-v1','qwen-contract-analysis-v2',"
        "'qwen-contract-analysis-v3'))"
    )
    op.execute(
        "CREATE INDEX ix_durable_jobs_successor_lineage ON workspace.durable_jobs "
        "(organization_id,workspace_id,causation_id,job_kind,input_digest,subject_document_id) "
        "INCLUDE (job_id,state) WHERE causation_id IS NOT NULL"
    )
    op.execute(
        "CREATE INDEX ix_durable_jobs_workspace_model_service ON workspace.durable_jobs "
        "(organization_id,workspace_id,started_at DESC) "
        "WHERE started_at IS NOT NULL AND job_kind IN ("
        "'OCR_EXTRACTION','DOCUMENT_PAGE_CLASSIFICATION',"
        "'PROJECT_DEFINITION_EXTRACTION','WORK_QUANTITY_MATERIAL_EXTRACTION',"
        "'PROJECT_STRUCTURE_RECONCILIATION','PROJECT_WORK_RECONCILIATION',"
        "'CONTRACT_ANALYSIS')"
    )
    op.execute(
        "CREATE INDEX ix_project_stage_source_terminal ON "
        "workspace.project_understanding_stage_results "
        "(organization_id,workspace_id,source_version_id,stage_kind,terminal_status)"
    )
    op.execute(
        "CREATE INDEX ix_assistant_turns_workspace_active ON workspace.assistant_turns "
        "(organization_id,workspace_id) WHERE state IN ('queued','leased','running') "
        "AND cancellation_requested=false"
    )


def downgrade() -> None:
    if os.environ.get("ASD_ALLOW_DESTRUCTIVE_DOWNGRADE") != "1":
        raise RuntimeError("Contract-v3 claim-performance downgrade requires a disposable database")
    op.execute("DROP INDEX workspace.ix_assistant_turns_workspace_active")
    op.execute("DROP INDEX workspace.ix_project_stage_source_terminal")
    op.execute("DROP INDEX workspace.ix_durable_jobs_workspace_model_service")
    op.execute("DROP INDEX workspace.ix_durable_jobs_successor_lineage")
    op.execute(
        "ALTER TABLE workspace.contract_analysis_results "
        "DROP CONSTRAINT contract_analysis_results_profile_version_check"
    )
    op.execute(
        "ALTER TABLE workspace.contract_analysis_results ADD CONSTRAINT "
        "contract_analysis_results_profile_version_check "
        "CHECK (profile_version='qwen-contract-analysis-v1')"
    )
