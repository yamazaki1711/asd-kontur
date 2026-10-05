"""Admit the partial controller-risk recovery contract profile.

Revision ID: 0106_contract_partial_risk_recovery
Revises: 0105_contract_controller_grounding
"""

from __future__ import annotations

import os

from alembic import op

revision = "0106_contract_partial_risk_recovery"
down_revision = "0105_contract_controller_grounding"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE workspace.contract_analysis_results "
        "DROP CONSTRAINT contract_analysis_results_profile_version_check"
    )
    op.execute(
        "ALTER TABLE workspace.contract_analysis_results ADD CONSTRAINT "
        "contract_analysis_results_profile_version_check CHECK (profile_version IN ("
        "'qwen-contract-analysis-v1','qwen-contract-analysis-v2',"
        "'qwen-contract-analysis-v3','qwen-contract-analysis-v4',"
        "'qwen-contract-analysis-v5','qwen-contract-analysis-v6',"
        "'qwen-contract-analysis-v7','qwen-contract-analysis-v8',"
        "'qwen-contract-analysis-v9'))"
    )


def downgrade() -> None:
    if os.environ.get("ASD_ALLOW_DESTRUCTIVE_DOWNGRADE") != "1":
        raise RuntimeError(
            "Contract partial-risk recovery downgrade requires a disposable database"
        )
    op.execute(
        "ALTER TABLE workspace.contract_analysis_results "
        "DROP CONSTRAINT contract_analysis_results_profile_version_check"
    )
    op.execute(
        "ALTER TABLE workspace.contract_analysis_results ADD CONSTRAINT "
        "contract_analysis_results_profile_version_check CHECK (profile_version IN ("
        "'qwen-contract-analysis-v1','qwen-contract-analysis-v2',"
        "'qwen-contract-analysis-v3','qwen-contract-analysis-v4',"
        "'qwen-contract-analysis-v5','qwen-contract-analysis-v6',"
        "'qwen-contract-analysis-v7','qwen-contract-analysis-v8'))"
    )
