"""Apply workspace fairness before per-workspace processing priority.

Revision ID: 0090_fair_workspace_before_processing_tier
Revises: 0089_material_semantics_profile_v18
"""

from __future__ import annotations

import os

import sqlalchemy as sa
from alembic import op

revision = "0090_fair_workspace_before_processing_tier"
down_revision = "0089_material_semantics_profile_v18"
branch_labels = None
depends_on = None

_PROCESSING_TIER = """CASE WHEN EXISTS (
               SELECT 1 FROM workspace.document_processing_states pending
                WHERE pending.organization_id=j.organization_id
                  AND pending.workspace_id=j.workspace_id
                  AND pending.extraction_status IN ('not_started','running')
                  AND pending.state_sequence=(
                    SELECT max(current_state.state_sequence)
                      FROM workspace.document_processing_states current_state
                     WHERE current_state.organization_id=pending.organization_id
                       AND current_state.workspace_id=pending.workspace_id
                       AND current_state.document_id=pending.document_id
                       AND current_state.document_version=pending.document_version
                  )
             ) THEN 2
             WHEN j.job_kind='PROJECT_UNDERSTANDING_RECONCILIATION'
                  AND j.input_manifest ? 'incremental_source_job_id' THEN 1
             ELSE 0 END DESC"""

_WORKSPACE_FAIRNESS = """COALESCE((
               SELECT max(served.started_at)
                 FROM workspace.durable_jobs served
                WHERE served.organization_id=j.organization_id
                  AND served.workspace_id=j.workspace_id
             ),'-infinity'::timestamptz) ASC"""

_OLD_ORDER = f"""{_PROCESSING_TIER},
             {_WORKSPACE_FAIRNESS},
             j.priority DESC,j.created_at,j.job_id"""

_NEW_ORDER = f"""{_WORKSPACE_FAIRNESS},
             {_PROCESSING_TIER},
             j.priority DESC,j.created_at,j.job_id"""


def _replace_order(source: str, target: str) -> None:
    connection = op.get_bind()
    definition = connection.scalar(
        sa.text(
            "SELECT pg_get_functiondef("
            "'workspace.claim_next_durable_job(text,integer)'::regprocedure)"
        )
    )
    if not isinstance(definition, str) or source not in definition:
        raise RuntimeError("workspace-fair claim ordering unavailable")
    connection.execute(sa.text(definition.replace(source, target)))


def upgrade() -> None:
    """Choose the least-recently-served workspace before its internal job tier."""

    _replace_order(_OLD_ORDER, _NEW_ORDER)


def downgrade() -> None:
    if os.environ.get("ASD_ALLOW_DESTRUCTIVE_DOWNGRADE") != "1":
        raise RuntimeError("Fair-workspace ordering downgrade requires a disposable database")
    _replace_order(_NEW_ORDER, _OLD_ORDER)
