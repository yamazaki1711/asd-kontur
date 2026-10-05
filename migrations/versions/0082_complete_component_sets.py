"""Require explicit complete component sets for quantity arithmetic.

Revision ID: 0082_complete_component_sets
Revises: 0081_quantity_relationship_output_budget
"""

from __future__ import annotations

import os

from alembic import op

revision = "0082_complete_component_sets"
down_revision = "0081_quantity_relationship_output_budget"
branch_labels = None
depends_on = None


_V3_TO_V14 = ",".join(f"'qwen-project-work-reconciliation-v{value}'" for value in range(3, 15))
_V3_TO_V13 = ",".join(f"'qwen-project-work-reconciliation-v{value}'" for value in range(3, 14))


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
    _replace_profile_constraint(_V3_TO_V14)


def downgrade() -> None:
    if os.environ.get("ASD_ALLOW_DESTRUCTIVE_DOWNGRADE") != "1":
        raise RuntimeError("Component-set downgrade requires a disposable database")
    if (
        op.get_bind()
        .exec_driver_sql(
            "SELECT EXISTS (SELECT 1 FROM workspace.project_work_reconciliation_results "
            "WHERE profile_version='qwen-project-work-reconciliation-v14')"
        )
        .scalar()
    ):
        raise RuntimeError("Cannot downgrade while v14 relationship results exist")
    _replace_profile_constraint(_V3_TO_V13)
