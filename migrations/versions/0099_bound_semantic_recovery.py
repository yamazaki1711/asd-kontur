"""Bound semantic recovery and ignore superseded active project chains.

Revision ID: 0099_bound_semantic_recovery
Revises: 0098_contract_v3_claim_perf
"""

from __future__ import annotations

import os

import sqlalchemy as sa
from alembic import op

revision = "0099_bound_semantic_recovery"
down_revision = "0098_contract_v3_claim_perf"
branch_labels = None
depends_on = None

_CLAIM_ANCHOR = """             AND j.cancellation_state='none'
             AND j.attempt_count < j.max_attempts"""

_SUPERSEDED_FILTER = """             AND j.cancellation_state='none'
             AND (j.job_kind NOT IN (
                   'PROJECT_UNDERSTANDING_RECONCILIATION',
                   'PROJECT_STRUCTURE_RECONCILIATION'
                 ) OR NOT EXISTS (
                   SELECT 1 FROM workspace.durable_jobs newer
                    WHERE newer.organization_id=j.organization_id
                      AND newer.workspace_id=j.workspace_id
                      AND newer.job_kind=j.job_kind
                      AND newer.state IN ('queued','leased','running')
                      AND (newer.created_at,newer.job_id)>(j.created_at,j.job_id)
                 ))
             AND j.attempt_count < j.max_attempts"""


def _replace_claim_filter(source: str, target: str) -> None:
    connection = op.get_bind()
    definition = connection.scalar(
        sa.text(
            "SELECT pg_get_functiondef("
            "'workspace.claim_next_durable_job(text,integer)'::regprocedure)"
        )
    )
    if not isinstance(definition, str) or source not in definition:
        raise RuntimeError("durable-job claim filter unavailable")
    connection.execute(sa.text(definition.replace(source, target)))


def upgrade() -> None:
    """Keep only the newest active materialization chain claimable per workspace."""

    op.execute(
        "CREATE INDEX ix_durable_jobs_active_project_recency ON workspace.durable_jobs "
        "(organization_id,workspace_id,job_kind,created_at DESC,job_id DESC) "
        "WHERE state IN ('queued','leased','running') AND job_kind IN ("
        "'PROJECT_UNDERSTANDING_RECONCILIATION','PROJECT_STRUCTURE_RECONCILIATION')"
    )
    _replace_claim_filter(_CLAIM_ANCHOR, _SUPERSEDED_FILTER)


def downgrade() -> None:
    if os.environ.get("ASD_ALLOW_DESTRUCTIVE_DOWNGRADE") != "1":
        raise RuntimeError("Semantic-recovery downgrade requires a disposable database")
    _replace_claim_filter(_SUPERSEDED_FILTER, _CLAIM_ANCHOR)
    op.execute("DROP INDEX workspace.ix_durable_jobs_active_project_recency")
