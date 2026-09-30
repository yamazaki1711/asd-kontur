"""Require explicit cross-document quantity scope decisions.

Revision ID: 0083_explicit_quantity_scope_decisions
Revises: 0082_complete_component_sets
"""

from __future__ import annotations

import os

from alembic import op

revision = "0083_explicit_quantity_scope_decisions"
down_revision = "0082_complete_component_sets"
branch_labels = None
depends_on = None


_V3_TO_V15 = ",".join(f"'qwen-project-work-reconciliation-v{value}'" for value in range(3, 16))
_V3_TO_V14 = ",".join(f"'qwen-project-work-reconciliation-v{value}'" for value in range(3, 15))


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
    _replace_profile_constraint(_V3_TO_V15)


def downgrade() -> None:
    if os.environ.get("ASD_ALLOW_DESTRUCTIVE_DOWNGRADE") != "1":
        raise RuntimeError("Quantity-scope downgrade requires a disposable database")
    if (
        op.get_bind()
        .exec_driver_sql(
            "SELECT EXISTS (SELECT 1 FROM workspace.project_work_reconciliation_results "
            "WHERE profile_version='qwen-project-work-reconciliation-v15')"
        )
        .scalar()
    ):
        raise RuntimeError("Cannot downgrade while v15 relationship results exist")
    _replace_profile_constraint(_V3_TO_V14)
