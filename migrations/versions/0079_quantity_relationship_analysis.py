"""Allow dedicated quantity-relationship reconciliation outputs.

Revision ID: 0079_quantity_relationship_analysis
Revises: 0078_cross_document_scope_reconciliation
"""

from __future__ import annotations

import os

from alembic import op

revision = "0079_quantity_relationship_analysis"
down_revision = "0078_cross_document_scope_reconciliation"
branch_labels = None
depends_on = None


_V3_TO_V11 = ",".join(f"'qwen-project-work-reconciliation-v{value}'" for value in range(3, 12))
_V3_TO_V10 = ",".join(f"'qwen-project-work-reconciliation-v{value}'" for value in range(3, 11))


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
    _replace_profile_constraint(_V3_TO_V11)


def downgrade() -> None:
    if os.environ.get("ASD_ALLOW_DESTRUCTIVE_DOWNGRADE") != "1":
        raise RuntimeError("Quantity-relationship downgrade requires a disposable database")
    if (
        op.get_bind()
        .exec_driver_sql(
            "SELECT EXISTS (SELECT 1 FROM workspace.project_work_reconciliation_results "
            "WHERE profile_version='qwen-project-work-reconciliation-v11')"
        )
        .scalar()
    ):
        raise RuntimeError("Cannot downgrade while quantity-relationship results exist")
    _replace_profile_constraint(_V3_TO_V10)
