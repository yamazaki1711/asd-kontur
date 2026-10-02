"""Admit the source-unit-preserving work reconciliation profile.

Revision ID: 0108_scaled_quantity_unit_profile
Revises: 0107_contract_directed_change_risk
"""

from __future__ import annotations

import os

from alembic import op

revision = "0108_scaled_quantity_unit_profile"
down_revision = "0107_contract_directed_change_risk"
branch_labels = None
depends_on = None


_V3_TO_V21 = ",".join(f"'qwen-project-work-reconciliation-v{value}'" for value in range(3, 22))
_V3_TO_V20 = ",".join(f"'qwen-project-work-reconciliation-v{value}'" for value in range(3, 21))


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
    _replace_profile_constraint(_V3_TO_V21)


def downgrade() -> None:
    if os.environ.get("ASD_ALLOW_DESTRUCTIVE_DOWNGRADE") != "1":
        raise RuntimeError("Scaled quantity-unit downgrade requires a disposable database")
    if (
        op.get_bind()
        .exec_driver_sql(
            "SELECT EXISTS (SELECT 1 FROM workspace.project_work_reconciliation_results "
            "WHERE profile_version='qwen-project-work-reconciliation-v21')"
        )
        .scalar()
    ):
        raise RuntimeError("Cannot downgrade while v21 reconciliation results exist")
    _replace_profile_constraint(_V3_TO_V20)
