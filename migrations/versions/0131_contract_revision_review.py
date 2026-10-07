"""Allow source-bound human review of proposed contract revisions.

Revision ID: 0131_contract_revision_review
Revises: 0130_contract_obligation_review
"""

from __future__ import annotations

import os

from alembic import op

revision = "0131_contract_revision_review"
down_revision = "0130_contract_obligation_review"
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
        "'contract_obligation','contract_revision'))"
    )


def downgrade() -> None:
    if os.environ.get("ASD_ALLOW_DESTRUCTIVE_DOWNGRADE") != "1":
        raise RuntimeError("Contract revision review downgrade requires a disposable database")
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
