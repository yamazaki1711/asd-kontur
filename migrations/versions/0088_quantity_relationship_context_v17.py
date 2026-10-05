"""Admit the explicit quantity-peer context reconciliation profile v17.

Revision ID: 0088_quantity_relationship_context_v17
Revises: 0087_quantity_semantics_profile_v16
"""

from __future__ import annotations

import os

from alembic import op

revision = "0088_quantity_relationship_context_v17"
down_revision = "0087_quantity_semantics_profile_v16"
branch_labels = None
depends_on = None


_V3_TO_V17 = ",".join(f"'qwen-project-work-reconciliation-v{value}'" for value in range(3, 18))
_V3_TO_V16 = ",".join(f"'qwen-project-work-reconciliation-v{value}'" for value in range(3, 17))


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
    _replace_profile_constraint(_V3_TO_V17)


def downgrade() -> None:
    if os.environ.get("ASD_ALLOW_DESTRUCTIVE_DOWNGRADE") != "1":
        raise RuntimeError("Quantity relationship profile downgrade requires a disposable database")
    if (
        op.get_bind()
        .exec_driver_sql(
            "SELECT EXISTS (SELECT 1 FROM workspace.project_work_reconciliation_results "
            "WHERE profile_version='qwen-project-work-reconciliation-v17')"
        )
        .scalar()
    ):
        raise RuntimeError("Cannot downgrade while v17 reconciliation results exist")
    _replace_profile_constraint(_V3_TO_V16)
