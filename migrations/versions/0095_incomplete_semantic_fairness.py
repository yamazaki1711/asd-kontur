"""Fair-share model time among semantically incomplete projects.

Revision ID: 0095_incomplete_semantic_fairness
Revises: 0094_intake_before_fairness
"""

from __future__ import annotations

import os

import sqlalchemy as sa
from alembic import op

revision = "0095_incomplete_semantic_fairness"
down_revision = "0094_intake_before_fairness"
branch_labels = None
depends_on = None

_SEMANTIC_COMPLETION_RATIO = """COALESCE((
               SELECT count(*) FILTER (WHERE EXISTS (
                        SELECT 1
                          FROM workspace.project_understanding_stage_results semantic_result
                         WHERE semantic_result.organization_id=active_version.organization_id
                           AND semantic_result.workspace_id=active_version.workspace_id
                           AND semantic_result.source_version_id=active_version.source_version_id
                           AND semantic_result.stage_kind='PROJECT_DEFINITION_EXTRACTION'
                           AND semantic_result.terminal_status IN ('complete','partial')
                      ))::numeric / NULLIF(count(*),0)
                 FROM workspace.document_versions active_version
                 JOIN workspace.document_version_activation_decisions activation
                   ON activation.organization_id=active_version.organization_id
                  AND activation.workspace_id=active_version.workspace_id
                  AND activation.document_id=active_version.document_id
                  AND activation.selected_document_version=active_version.version
                WHERE active_version.organization_id=j.organization_id
                  AND active_version.workspace_id=j.workspace_id
                  AND NOT EXISTS (
                    SELECT 1
                      FROM workspace.document_version_activation_decisions newer
                     WHERE newer.organization_id=activation.organization_id
                       AND newer.workspace_id=activation.workspace_id
                       AND newer.document_id=activation.document_id
                       AND newer.decision_version>activation.decision_version
                  )
             ),1) ASC,
             """


def _replace(source: str, target: str) -> None:
    connection = op.get_bind()
    definition = connection.scalar(
        sa.text(
            "SELECT pg_get_functiondef("
            "'workspace.claim_next_durable_job(text,integer)'::regprocedure)"
        )
    )
    if not isinstance(definition, str) or source not in definition:
        raise RuntimeError("semantic completion ratio claim ordering unavailable")
    connection.execute(sa.text(definition.replace(source, target)))


def upgrade() -> None:
    """Retain incomplete-project priority without letting one project monopolize Qwen."""

    _replace(_SEMANTIC_COMPLETION_RATIO, "")


def downgrade() -> None:
    if os.environ.get("ASD_ALLOW_DESTRUCTIVE_DOWNGRADE") != "1":
        raise RuntimeError("Semantic-fairness downgrade requires a disposable database")
    fairness = "COALESCE((\n               SELECT max(served.started_at)"
    _replace(fairness, _SEMANTIC_COMPLETION_RATIO + fairness)
