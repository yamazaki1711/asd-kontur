"""Version the measured quantity-relationship output budget.

Revision ID: 0081_quantity_relationship_output_budget
Revises: 0080_relationship_context_integrity
"""

from __future__ import annotations

import os

from alembic import op

revision = "0081_quantity_relationship_output_budget"
down_revision = "0080_relationship_context_integrity"
branch_labels = None
depends_on = None


_V3_TO_V13 = ",".join(f"'qwen-project-work-reconciliation-v{value}'" for value in range(3, 14))
_V3_TO_V12 = ",".join(f"'qwen-project-work-reconciliation-v{value}'" for value in range(3, 13))


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
    _replace_profile_constraint(_V3_TO_V13)


def downgrade() -> None:
    if os.environ.get("ASD_ALLOW_DESTRUCTIVE_DOWNGRADE") != "1":
        raise RuntimeError("Quantity-relationship budget downgrade requires a disposable database")
    if (
        op.get_bind()
        .exec_driver_sql(
            "SELECT EXISTS (SELECT 1 FROM workspace.project_work_reconciliation_results "
            "WHERE profile_version='qwen-project-work-reconciliation-v13')"
        )
        .scalar()
    ):
        raise RuntimeError("Cannot downgrade while v13 relationship results exist")
    _replace_profile_constraint(_V3_TO_V12)
