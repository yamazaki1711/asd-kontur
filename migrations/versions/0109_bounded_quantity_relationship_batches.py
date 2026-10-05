"""Admit the measured two-row quantity-relationship profile.

Revision ID: 0109_bounded_quantity_relationship_batches
Revises: 0108_scaled_quantity_unit_profile
"""

from __future__ import annotations

import os

from alembic import op

revision = "0109_bounded_quantity_relationship_batches"
down_revision = "0108_scaled_quantity_unit_profile"
branch_labels = None
depends_on = None


_V3_TO_V22 = ",".join(f"'qwen-project-work-reconciliation-v{value}'" for value in range(3, 23))
_V3_TO_V21 = ",".join(f"'qwen-project-work-reconciliation-v{value}'" for value in range(3, 22))


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
    _replace_profile_constraint(_V3_TO_V22)


def downgrade() -> None:
    if os.environ.get("ASD_ALLOW_DESTRUCTIVE_DOWNGRADE") != "1":
        raise RuntimeError("Bounded quantity-relationship downgrade requires a disposable database")
    if (
        op.get_bind()
        .exec_driver_sql(
            "SELECT EXISTS (SELECT 1 FROM workspace.project_work_reconciliation_results "
            "WHERE profile_version='qwen-project-work-reconciliation-v22')"
        )
        .scalar()
    ):
        raise RuntimeError("Cannot downgrade while v22 reconciliation results exist")
    _replace_profile_constraint(_V3_TO_V21)
