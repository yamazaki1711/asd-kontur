"""Admit complete-context relationship schema repair profile v20.

Revision ID: 0093_relationship_schema_repair_v20
Revises: 0092_relationship_review_budget_v19
"""

from __future__ import annotations

import os

from alembic import op

revision = "0093_relationship_schema_repair_v20"
down_revision = "0092_relationship_review_budget_v19"
branch_labels = None
depends_on = None


_V3_TO_V20 = ",".join(f"'qwen-project-work-reconciliation-v{value}'" for value in range(3, 21))
_V3_TO_V19 = ",".join(f"'qwen-project-work-reconciliation-v{value}'" for value in range(3, 20))


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
    _replace_profile_constraint(_V3_TO_V20)


def downgrade() -> None:
    if os.environ.get("ASD_ALLOW_DESTRUCTIVE_DOWNGRADE") != "1":
        raise RuntimeError("Relationship schema-repair downgrade requires a disposable database")
    if (
        op.get_bind()
        .exec_driver_sql(
            "SELECT EXISTS (SELECT 1 FROM workspace.project_work_reconciliation_results "
            "WHERE profile_version='qwen-project-work-reconciliation-v20')"
        )
        .scalar()
    ):
        raise RuntimeError("Cannot downgrade while v20 reconciliation results exist")
    _replace_profile_constraint(_V3_TO_V19)
