"""Admit exact compound source-measure option profile.

Revision ID: 0116_exact_compound_source_measure_options
Revises: 0115_typed_quantity_relationship_repair
"""

from __future__ import annotations

import os

from alembic import op

revision = "0116_exact_compound_source_measure_options"
down_revision = "0115_typed_quantity_relationship_repair"
branch_labels = None
depends_on = None


_V3_TO_V29 = ",".join(f"'qwen-project-work-reconciliation-v{value}'" for value in range(3, 30))
_V3_TO_V28 = ",".join(f"'qwen-project-work-reconciliation-v{value}'" for value in range(3, 29))


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
    _replace_profile_constraint(_V3_TO_V29)


def downgrade() -> None:
    if os.environ.get("ASD_ALLOW_DESTRUCTIVE_DOWNGRADE") != "1":
        raise RuntimeError("Compound source-measure downgrade requires a disposable database")
    if (
        op.get_bind()
        .exec_driver_sql(
            "SELECT EXISTS (SELECT 1 FROM workspace.project_work_reconciliation_results "
            "WHERE profile_version='qwen-project-work-reconciliation-v29')"
        )
        .scalar()
    ):
        raise RuntimeError("Cannot downgrade while v29 reconciliation results exist")
    _replace_profile_constraint(_V3_TO_V28)
