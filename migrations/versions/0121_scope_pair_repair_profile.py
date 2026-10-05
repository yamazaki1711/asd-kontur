"""Admit intact exact work-pair repair profile.

Revision ID: 0121_scope_pair_repair_profile
Revises: 0120_pair_specific_work_scope_profile
"""

from __future__ import annotations

import os

from alembic import op

revision = "0121_scope_pair_repair_profile"
down_revision = "0120_pair_specific_work_scope_profile"
branch_labels = None
depends_on = None


_V3_TO_V34 = ",".join(f"'qwen-project-work-reconciliation-v{value}'" for value in range(3, 35))
_V3_TO_V33 = ",".join(f"'qwen-project-work-reconciliation-v{value}'" for value in range(3, 34))


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
    _replace_profile_constraint(_V3_TO_V34)


def downgrade() -> None:
    if os.environ.get("ASD_ALLOW_DESTRUCTIVE_DOWNGRADE") != "1":
        raise RuntimeError("Scope-pair repair downgrade requires a disposable database")
    if (
        op.get_bind()
        .exec_driver_sql(
            "SELECT EXISTS (SELECT 1 FROM workspace.project_work_reconciliation_results "
            "WHERE profile_version='qwen-project-work-reconciliation-v34')"
        )
        .scalar()
    ):
        raise RuntimeError("Cannot downgrade while v34 reconciliation results exist")
    _replace_profile_constraint(_V3_TO_V33)
