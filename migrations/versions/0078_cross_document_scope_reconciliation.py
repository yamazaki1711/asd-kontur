"""Allow cross-document scope-reconciliation outputs.

Revision ID: 0078_cross_document_scope_reconciliation
Revises: 0077_generalized_tender_quantity_semantics
"""

from __future__ import annotations

import os

from alembic import op

revision = "0078_cross_document_scope_reconciliation"
down_revision = "0077_generalized_tender_quantity_semantics"
branch_labels = None
depends_on = None


_V3_TO_V10 = (
    "'qwen-project-work-reconciliation-v3','qwen-project-work-reconciliation-v4',"
    "'qwen-project-work-reconciliation-v5','qwen-project-work-reconciliation-v6',"
    "'qwen-project-work-reconciliation-v7','qwen-project-work-reconciliation-v8',"
    "'qwen-project-work-reconciliation-v9','qwen-project-work-reconciliation-v10'"
)
_V3_TO_V9 = (
    "'qwen-project-work-reconciliation-v3','qwen-project-work-reconciliation-v4',"
    "'qwen-project-work-reconciliation-v5','qwen-project-work-reconciliation-v6',"
    "'qwen-project-work-reconciliation-v7','qwen-project-work-reconciliation-v8',"
    "'qwen-project-work-reconciliation-v9'"
)


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
    _replace_profile_constraint(_V3_TO_V10)


def downgrade() -> None:
    if os.environ.get("ASD_ALLOW_DESTRUCTIVE_DOWNGRADE") != "1":
        raise RuntimeError(
            "Cross-document scope-reconciliation downgrade requires a disposable database"
        )
    if (
        op.get_bind()
        .exec_driver_sql(
            "SELECT EXISTS (SELECT 1 FROM workspace.project_work_reconciliation_results WHERE "
            "profile_version='qwen-project-work-reconciliation-v10')"
        )
        .scalar()
    ):
        raise RuntimeError("Cannot downgrade while cross-document reconciliation results exist")
    _replace_profile_constraint(_V3_TO_V9)
