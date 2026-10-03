"""Prevent one mature workspace from starving another workspace's analysis.

Revision ID: 0086_workspace_fair_job_claim
Revises: 0085_incomplete_project_time_to_first_result
"""

from __future__ import annotations

import os

import sqlalchemy as sa
from alembic import op

revision = "0086_workspace_fair_job_claim"
down_revision = "0085_incomplete_project_time_to_first_result"
branch_labels = None
depends_on = None

_PRIORITY_TAIL = """ELSE 0 END DESC,
             j.priority DESC,j.created_at,j.job_id"""

_FAIR_PRIORITY_TAIL = """ELSE 0 END DESC,
             COALESCE((
               SELECT max(served.started_at)
                 FROM workspace.durable_jobs served
                WHERE served.organization_id=j.organization_id
                  AND served.workspace_id=j.workspace_id
             ),'-infinity'::timestamptz) ASC,
             j.priority DESC,j.created_at,j.job_id"""


def upgrade() -> None:
    """Select the least-recently-served eligible workspace before job priority."""

    connection = op.get_bind()
    definition = connection.scalar(
        sa.text(
            "SELECT pg_get_functiondef("
            "'workspace.claim_next_durable_job(text,integer)'::regprocedure)"
        )
    )
    if not isinstance(definition, str) or _PRIORITY_TAIL not in definition:
        raise RuntimeError("0085 claim priority definition unavailable")
    connection.execute(sa.text(definition.replace(_PRIORITY_TAIL, _FAIR_PRIORITY_TAIL)))


def downgrade() -> None:
    if os.environ.get("ASD_ALLOW_DESTRUCTIVE_DOWNGRADE") != "1":
        raise RuntimeError("Workspace-fair claim downgrade requires a disposable database")
    connection = op.get_bind()
    definition = connection.scalar(
        sa.text(
            "SELECT pg_get_functiondef("
            "'workspace.claim_next_durable_job(text,integer)'::regprocedure)"
        )
    )
    if not isinstance(definition, str) or _FAIR_PRIORITY_TAIL not in definition:
        raise RuntimeError("0086 claim priority definition unavailable")
    connection.execute(sa.text(definition.replace(_FAIR_PRIORITY_TAIL, _PRIORITY_TAIL)))
