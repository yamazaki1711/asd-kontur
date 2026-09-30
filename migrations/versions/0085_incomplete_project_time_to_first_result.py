"""Keep incomplete project intake ahead of deep historical analysis.

Revision ID: 0085_incomplete_project_time_to_first_result
Revises: 0084_new_project_time_to_first_result
"""

from __future__ import annotations

import os
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

import sqlalchemy as sa
from alembic import op

revision = "0085_incomplete_project_time_to_first_result"
down_revision = "0084_new_project_time_to_first_result"
branch_labels = None
depends_on = None

_INITIAL_PROJECT_PRIORITY = """CASE WHEN NOT EXISTS (
               SELECT 1 FROM workspace.document_processing_states processed
                WHERE processed.organization_id=j.organization_id
                  AND processed.workspace_id=j.workspace_id
                  AND processed.extraction_status IN (
                    'complete','partial_with_capability_gap'
                  )
             ) THEN 2"""

_INCOMPLETE_PROJECT_PRIORITY = """CASE WHEN EXISTS (
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
             ) THEN 2"""


def _previous_migration():
    specification = spec_from_file_location(
        "asd_kontur_migration_0084",
        Path(__file__).with_name("0084_new_project_time_to_first_result.py"),
    )
    if specification is None or specification.loader is None:
        raise RuntimeError("claim-function source unavailable")
    migration = module_from_spec(specification)
    specification.loader.exec_module(migration)
    return migration


def upgrade() -> None:
    """Prioritize every project with actively incomplete admitted documents."""

    connection = op.get_bind()
    definition = connection.scalar(
        sa.text(
            "SELECT pg_get_functiondef("
            "'workspace.claim_next_durable_job(text,integer)'::regprocedure)"
        )
    )
    if not isinstance(definition, str) or _INITIAL_PROJECT_PRIORITY not in definition:
        raise RuntimeError("0084 claim priority definition unavailable")
    connection.execute(sa.text(definition.replace(_INITIAL_PROJECT_PRIORITY, _INCOMPLETE_PROJECT_PRIORITY)))


def downgrade() -> None:
    if os.environ.get("ASD_ALLOW_DESTRUCTIVE_DOWNGRADE") != "1":
        raise RuntimeError("Incomplete-project priority downgrade requires a disposable database")
    _previous_migration().upgrade()
