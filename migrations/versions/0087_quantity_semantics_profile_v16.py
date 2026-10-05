"""Admit the bounded quantity-semantics reconciliation profile v16.

Revision ID: 0087_quantity_semantics_profile_v16
Revises: 0086_workspace_fair_job_claim
"""

from __future__ import annotations

import os

from alembic import op

revision = "0087_quantity_semantics_profile_v16"
down_revision = "0086_workspace_fair_job_claim"
branch_labels = None
depends_on = None


_V3_TO_V16 = ",".join(f"'qwen-project-work-reconciliation-v{value}'" for value in range(3, 17))
_V3_TO_V15 = ",".join(f"'qwen-project-work-reconciliation-v{value}'" for value in range(3, 16))


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
    _replace_profile_constraint(_V3_TO_V16)


def downgrade() -> None:
    if os.environ.get("ASD_ALLOW_DESTRUCTIVE_DOWNGRADE") != "1":
        raise RuntimeError("Quantity-semantics profile downgrade requires a disposable database")
    if (
        op.get_bind()
        .exec_driver_sql(
            "SELECT EXISTS (SELECT 1 FROM workspace.project_work_reconciliation_results "
            "WHERE profile_version='qwen-project-work-reconciliation-v16')"
        )
        .scalar()
    ):
        raise RuntimeError("Cannot downgrade while v16 reconciliation results exist")
    _replace_profile_constraint(_V3_TO_V15)
