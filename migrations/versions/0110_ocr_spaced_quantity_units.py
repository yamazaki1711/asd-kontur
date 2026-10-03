"""Admit OCR-spaced source-unit normalization.

Revision ID: 0110_ocr_spaced_quantity_units
Revises: 0109_bounded_quantity_relationship_batches
"""

from __future__ import annotations

import os

from alembic import op

revision = "0110_ocr_spaced_quantity_units"
down_revision = "0109_bounded_quantity_relationship_batches"
branch_labels = None
depends_on = None


_V3_TO_V23 = ",".join(f"'qwen-project-work-reconciliation-v{value}'" for value in range(3, 24))
_V3_TO_V22 = ",".join(f"'qwen-project-work-reconciliation-v{value}'" for value in range(3, 23))


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
    _replace_profile_constraint(_V3_TO_V23)


def downgrade() -> None:
    if os.environ.get("ASD_ALLOW_DESTRUCTIVE_DOWNGRADE") != "1":
        raise RuntimeError("OCR-spaced source-unit downgrade requires a disposable database")
    if (
        op.get_bind()
        .exec_driver_sql(
            "SELECT EXISTS (SELECT 1 FROM workspace.project_work_reconciliation_results "
            "WHERE profile_version='qwen-project-work-reconciliation-v23')"
        )
        .scalar()
    ):
        raise RuntimeError("Cannot downgrade while v23 reconciliation results exist")
    _replace_profile_constraint(_V3_TO_V22)
