"""Require an explicit contractor-risk mechanism.

Revision ID: 0103_contract_risk_mechanism
Revises: 0102_contract_explicit_risk_basis
"""

from __future__ import annotations

import os

from alembic import op

revision = "0103_contract_risk_mechanism"
down_revision = "0102_contract_explicit_risk_basis"
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
        "'qwen-contract-analysis-v5','qwen-contract-analysis-v6'))"
    )


def downgrade() -> None:
    if os.environ.get("ASD_ALLOW_DESTRUCTIVE_DOWNGRADE") != "1":
        raise RuntimeError("Contract-risk-mechanism downgrade requires a disposable database")
    op.execute(
        "ALTER TABLE workspace.contract_analysis_results "
        "DROP CONSTRAINT contract_analysis_results_profile_version_check"
    )
    op.execute(
        "ALTER TABLE workspace.contract_analysis_results ADD CONSTRAINT "
        "contract_analysis_results_profile_version_check CHECK (profile_version IN ("
        "'qwen-contract-analysis-v1','qwen-contract-analysis-v2',"
        "'qwen-contract-analysis-v3','qwen-contract-analysis-v4',"
        "'qwen-contract-analysis-v5'))"
    )
