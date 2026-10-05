"""Admit task-scoped quantity relationship profile.

Revision ID: 0127_task_scoped_quantity_profile
Revises: 0126_indivisible_quantity_pair_profile
"""

from __future__ import annotations

import os

from alembic import op

revision = "0127_task_scoped_quantity_profile"
down_revision = "0126_indivisible_quantity_pair_profile"
branch_labels = None
depends_on = None


_V3_TO_V40 = ",".join(f"'qwen-project-work-reconciliation-v{value}'" for value in range(3, 41))
_V3_TO_V39 = ",".join(f"'qwen-project-work-reconciliation-v{value}'" for value in range(3, 40))


def _replace_profile_constraint(allowed_profiles: str) -> None:
    op.execute(
        "ALTER TABLE workspace.project_work_reconciliation_results DROP CONSTRAINT "
        "project_work_reconciliation_results_profile_version_check"
    )
    op.execute(
        "ALTER TABLE workspace.project_work_reconciliation_results ADD CONSTRAINT "
        "project_work_reconciliation_results_profile_version_check "
        f"CHECK (profile_version IN ({allowed_profiles}))"
    )


def upgrade() -> None:
    _replace_profile_constraint(_V3_TO_V40)


def downgrade() -> None:
    if os.environ.get("ASD_ALLOW_DESTRUCTIVE_DOWNGRADE") != "1":
        raise RuntimeError("Task-scoped quantity profile downgrade requires a disposable database")
    if (
        op.get_bind()
        .exec_driver_sql(
            "SELECT EXISTS (SELECT 1 FROM workspace.project_work_reconciliation_results "
            "WHERE profile_version='qwen-project-work-reconciliation-v40')"
        )
        .scalar()
    ):
        raise RuntimeError("Cannot downgrade while v40 reconciliation results exist")
    _replace_profile_constraint(_V3_TO_V39)
