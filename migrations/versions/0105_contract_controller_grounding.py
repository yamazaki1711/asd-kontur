"""Admit the counterparty-grounded contract analysis profile.

Revision ID: 0105_contract_controller_grounding
Revises: 0104_contract_adverse_effect_text
"""

from __future__ import annotations

import os

from alembic import op

revision = "0105_contract_controller_grounding"
down_revision = "0104_contract_adverse_effect_text"
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
        "'qwen-contract-analysis-v7','qwen-contract-analysis-v8'))"
    )


def downgrade() -> None:
    if os.environ.get("ASD_ALLOW_DESTRUCTIVE_DOWNGRADE") != "1":
        raise RuntimeError("Contract controller-grounding downgrade requires a disposable database")
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
        "'qwen-contract-analysis-v7'))"
    )
