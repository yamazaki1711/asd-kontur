"""Allow commercial-scope-aware work reconciliation outputs.

Revision ID: 0072_commercial_work_reconciliation_profile
Revises: 0071_unresolved_work_reconciliation_profile
"""

from __future__ import annotations

import os

from alembic import op

revision = "0072_commercial_work_reconciliation_profile"
down_revision = "0071_unresolved_work_reconciliation_profile"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE workspace.project_work_reconciliation_results DROP CONSTRAINT "
        "project_work_reconciliation_results_profile_version_check"
    )
    op.execute(
        "ALTER TABLE workspace.project_work_reconciliation_results ADD CONSTRAINT "
        "project_work_reconciliation_results_profile_version_check CHECK (profile_version IN "
        "('qwen-project-work-reconciliation-v3','qwen-project-work-reconciliation-v4',"
        "'qwen-project-work-reconciliation-v5','qwen-project-work-reconciliation-v6',"
        "'qwen-project-work-reconciliation-v7','qwen-project-work-reconciliation-v8'))"
    )


def downgrade() -> None:
    if os.environ.get("ASD_ALLOW_DESTRUCTIVE_DOWNGRADE") != "1":
        raise RuntimeError(
            "Commercial-work reconciliation downgrade requires a disposable database"
        )
    if (
        op.get_bind()
        .exec_driver_sql(
            "SELECT EXISTS (SELECT 1 FROM workspace.project_work_reconciliation_results WHERE "
            "profile_version='qwen-project-work-reconciliation-v8')"
        )
        .scalar()
    ):
        raise RuntimeError("Cannot downgrade while commercial-work reconciliation results exist")
    op.execute(
        "ALTER TABLE workspace.project_work_reconciliation_results DROP CONSTRAINT "
        "project_work_reconciliation_results_profile_version_check"
    )
    op.execute(
        "ALTER TABLE workspace.project_work_reconciliation_results ADD CONSTRAINT "
        "project_work_reconciliation_results_profile_version_check CHECK (profile_version IN "
        "('qwen-project-work-reconciliation-v3','qwen-project-work-reconciliation-v4',"
        "'qwen-project-work-reconciliation-v5','qwen-project-work-reconciliation-v6',"
        "'qwen-project-work-reconciliation-v7'))"
    )
