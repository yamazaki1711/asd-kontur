"""Admit bounded progressive scope-pair repair profile.

Revision ID: 0125_progressive_scope_repair_profile
Revises: 0124_explicit_revision_scope_profile
"""

from __future__ import annotations

import os

from alembic import op

revision = "0125_progressive_scope_repair_profile"
down_revision = "0124_explicit_revision_scope_profile"
branch_labels = None
depends_on = None


_V3_TO_V38 = ",".join(f"'qwen-project-work-reconciliation-v{value}'" for value in range(3, 39))
_V3_TO_V37 = ",".join(f"'qwen-project-work-reconciliation-v{value}'" for value in range(3, 38))


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
    _replace_profile_constraint(_V3_TO_V38)


def downgrade() -> None:
    if os.environ.get("ASD_ALLOW_DESTRUCTIVE_DOWNGRADE") != "1":
        raise RuntimeError(
            "Progressive scope-repair profile downgrade requires a disposable database"
        )
    if (
        op.get_bind()
        .exec_driver_sql(
            "SELECT EXISTS (SELECT 1 FROM workspace.project_work_reconciliation_results "
            "WHERE profile_version='qwen-project-work-reconciliation-v38')"
        )
        .scalar()
    ):
        raise RuntimeError("Cannot downgrade while v38 reconciliation results exist")
    _replace_profile_constraint(_V3_TO_V37)
