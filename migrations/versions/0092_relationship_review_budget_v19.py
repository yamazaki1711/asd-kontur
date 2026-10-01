"""Admit complete-context relationship recovery profile v19.

Revision ID: 0092_relationship_review_budget_v19
Revises: 0091_model_slot_workspace_fairness
"""

from __future__ import annotations

import os

from alembic import op

revision = "0092_relationship_review_budget_v19"
down_revision = "0091_model_slot_workspace_fairness"
branch_labels = None
depends_on = None


_V3_TO_V19 = ",".join(f"'qwen-project-work-reconciliation-v{value}'" for value in range(3, 20))
_V3_TO_V18 = ",".join(f"'qwen-project-work-reconciliation-v{value}'" for value in range(3, 19))


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
    _replace_profile_constraint(_V3_TO_V19)


def downgrade() -> None:
    if os.environ.get("ASD_ALLOW_DESTRUCTIVE_DOWNGRADE") != "1":
        raise RuntimeError("Relationship-review profile downgrade requires a disposable database")
    if (
        op.get_bind()
        .exec_driver_sql(
            "SELECT EXISTS (SELECT 1 FROM workspace.project_work_reconciliation_results "
            "WHERE profile_version='qwen-project-work-reconciliation-v19')"
        )
        .scalar()
    ):
        raise RuntimeError("Cannot downgrade while v19 reconciliation results exist")
    _replace_profile_constraint(_V3_TO_V18)
