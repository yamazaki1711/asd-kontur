"""Measure workspace fairness on scarce model-bound turns.

Revision ID: 0091_model_slot_workspace_fairness
Revises: 0090_fair_workspace_before_processing_tier
"""

from __future__ import annotations

import os

import sqlalchemy as sa
from alembic import op

revision = "0091_model_slot_workspace_fairness"
down_revision = "0090_fair_workspace_before_processing_tier"
branch_labels = None
depends_on = None

_ALL_JOB_FAIRNESS = """SELECT max(served.started_at)
                 FROM workspace.durable_jobs served
                WHERE served.organization_id=j.organization_id
                  AND served.workspace_id=j.workspace_id"""

_MODEL_SLOT_FAIRNESS = """SELECT max(served.started_at)
                 FROM workspace.durable_jobs served
                WHERE served.organization_id=j.organization_id
                  AND served.workspace_id=j.workspace_id
                  AND served.job_kind IN (
                    'OCR_EXTRACTION','DOCUMENT_PAGE_CLASSIFICATION',
                    'PROJECT_DEFINITION_EXTRACTION','WORK_QUANTITY_MATERIAL_EXTRACTION',
                    'PROJECT_STRUCTURE_RECONCILIATION','PROJECT_WORK_RECONCILIATION'
                  )"""


def _replace_fairness(source: str, target: str) -> None:
    connection = op.get_bind()
    definition = connection.scalar(
        sa.text(
            "SELECT pg_get_functiondef("
            "'workspace.claim_next_durable_job(text,integer)'::regprocedure)"
        )
    )
    if not isinstance(definition, str) or source not in definition:
        raise RuntimeError("workspace fairness definition unavailable")
    connection.execute(sa.text(definition.replace(source, target)))


def upgrade() -> None:
    """Let cheap native stages drain without consuming a workspace model turn."""

    _replace_fairness(_ALL_JOB_FAIRNESS, _MODEL_SLOT_FAIRNESS)


def downgrade() -> None:
    if os.environ.get("ASD_ALLOW_DESTRUCTIVE_DOWNGRADE") != "1":
        raise RuntimeError("Model-slot fairness downgrade requires a disposable database")
    _replace_fairness(_MODEL_SLOT_FAIRNESS, _ALL_JOB_FAIRNESS)
