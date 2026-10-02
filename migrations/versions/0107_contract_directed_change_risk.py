"""Admit Customer-directed changed-work risk interpretation.

Revision ID: 0107_contract_directed_change_risk
Revises: 0106_contract_partial_risk_recovery
"""

from __future__ import annotations

import os

from alembic import op

revision = "0107_contract_directed_change_risk"
down_revision = "0106_contract_partial_risk_recovery"
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
        "'qwen-contract-analysis-v9','qwen-contract-analysis-v10'))"
    )


def downgrade() -> None:
    if os.environ.get("ASD_ALLOW_DESTRUCTIVE_DOWNGRADE") != "1":
        raise RuntimeError("Contract directed-change downgrade requires a disposable database")
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
