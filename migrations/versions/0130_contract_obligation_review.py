"""Allow workspace-scoped review of extracted contract obligations.

Revision ID: 0130_contract_obligation_review
Revises: 0129_contract_reference_review
"""

from __future__ import annotations

import os

from alembic import op

revision = "0130_contract_obligation_review"
down_revision = "0129_contract_reference_review"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE workspace.project_candidate_review_decisions "
        "DROP CONSTRAINT project_candidate_review_decisions_candidate_kind_check"
    )
    op.execute(
        "ALTER TABLE workspace.project_candidate_review_decisions ADD CONSTRAINT "
        "project_candidate_review_decisions_candidate_kind_check CHECK "
        "(candidate_kind IN ('project_field','work_type','quantity','material',"
        "'contract_obligation'))"
    )


def downgrade() -> None:
    if os.environ.get("ASD_ALLOW_DESTRUCTIVE_DOWNGRADE") != "1":
        raise RuntimeError("Contract obligation review downgrade requires a disposable database")
    op.execute(
        "ALTER TABLE workspace.project_candidate_review_decisions "
        "DROP CONSTRAINT project_candidate_review_decisions_candidate_kind_check"
    )
    op.execute(
        "ALTER TABLE workspace.project_candidate_review_decisions ADD CONSTRAINT "
        "project_candidate_review_decisions_candidate_kind_check CHECK "
        "(candidate_kind IN ('project_field','work_type','quantity','material'))"
    )
