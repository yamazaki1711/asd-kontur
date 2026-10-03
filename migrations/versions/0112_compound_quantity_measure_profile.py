"""Admit source-bound compound quantity measure review.

Revision ID: 0112_compound_quantity_measure_profile
Revises: 0111_reviewed_quantity_source_value
"""

from __future__ import annotations

import os

from alembic import op

revision = "0112_compound_quantity_measure_profile"
down_revision = "0111_reviewed_quantity_source_value"
branch_labels = None
depends_on = None


_V3_TO_V25 = ",".join(f"'qwen-project-work-reconciliation-v{value}'" for value in range(3, 26))
_V3_TO_V24 = ",".join(f"'qwen-project-work-reconciliation-v{value}'" for value in range(3, 25))


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
    _replace_profile_constraint(_V3_TO_V25)


def downgrade() -> None:
    if os.environ.get("ASD_ALLOW_DESTRUCTIVE_DOWNGRADE") != "1":
        raise RuntimeError("Compound quantity measure downgrade requires a disposable database")
    if (
        op.get_bind()
        .exec_driver_sql(
            "SELECT EXISTS (SELECT 1 FROM workspace.project_work_reconciliation_results "
            "WHERE profile_version='qwen-project-work-reconciliation-v25')"
        )
        .scalar()
    ):
        raise RuntimeError("Cannot downgrade while v25 reconciliation results exist")
    _replace_profile_constraint(_V3_TO_V24)
