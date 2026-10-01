"""Prioritize the first project fact, then fair-share deeper analysis.

Revision ID: 0096_first_fact_fairness
Revises: 0095_incomplete_semantic_fairness
"""

from __future__ import annotations

import os

import sqlalchemy as sa
from alembic import op

revision = "0096_first_fact_fairness"
down_revision = "0095_incomplete_semantic_fairness"
branch_labels = None
depends_on = None

_INCOMPLETE_PROJECT_TIER = """CASE WHEN EXISTS (
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
             ) OR EXISTS (
               SELECT 1
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
                  AND NOT EXISTS (
                    SELECT 1
                      FROM workspace.project_understanding_stage_results semantic_result
                     WHERE semantic_result.organization_id=active_version.organization_id
                       AND semantic_result.workspace_id=active_version.workspace_id
                       AND semantic_result.source_version_id=active_version.source_version_id
                       AND semantic_result.stage_kind='PROJECT_DEFINITION_EXTRACTION'
                       AND semantic_result.terminal_status IN ('complete','partial')
                  )
             ) THEN 2
             WHEN j.job_kind='PROJECT_UNDERSTANDING_RECONCILIATION'
                  AND j.input_manifest ? 'incremental_source_job_id' THEN 1
             ELSE 0 END DESC"""

_FIRST_PROJECT_FACT_TIER = """CASE WHEN (
               EXISTS (
                 SELECT 1
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
               )
               AND NOT EXISTS (
                 SELECT 1
                   FROM workspace.document_versions completed_version
                   JOIN workspace.document_version_activation_decisions completed_activation
                     ON completed_activation.organization_id=completed_version.organization_id
                    AND completed_activation.workspace_id=completed_version.workspace_id
                    AND completed_activation.document_id=completed_version.document_id
                    AND completed_activation.selected_document_version=completed_version.version
                   JOIN workspace.project_understanding_stage_results semantic_result
                     ON semantic_result.organization_id=completed_version.organization_id
                    AND semantic_result.workspace_id=completed_version.workspace_id
                    AND semantic_result.source_version_id=completed_version.source_version_id
                    AND semantic_result.stage_kind='PROJECT_DEFINITION_EXTRACTION'
                    AND semantic_result.terminal_status IN ('complete','partial')
                  WHERE completed_version.organization_id=j.organization_id
                    AND completed_version.workspace_id=j.workspace_id
                    AND NOT EXISTS (
                      SELECT 1
                        FROM workspace.document_version_activation_decisions newer
                       WHERE newer.organization_id=completed_activation.organization_id
                         AND newer.workspace_id=completed_activation.workspace_id
                         AND newer.document_id=completed_activation.document_id
                         AND newer.decision_version>completed_activation.decision_version
                    )
               )
             ) THEN 2
             ELSE 0 END DESC"""


def _replace(source: str, target: str) -> None:
    connection = op.get_bind()
    definition = connection.scalar(
        sa.text(
            "SELECT pg_get_functiondef("
            "'workspace.claim_next_durable_job(text,integer)'::regprocedure)"
        )
    )
    if not isinstance(definition, str) or source not in definition:
        raise RuntimeError("project-fact claim tier unavailable")
    connection.execute(sa.text(definition.replace(source, target)))


def upgrade() -> None:
    """Boost an unseen project only until its first semantic project fact exists."""

    _replace(_INCOMPLETE_PROJECT_TIER, _FIRST_PROJECT_FACT_TIER)


def downgrade() -> None:
    if os.environ.get("ASD_ALLOW_DESTRUCTIVE_DOWNGRADE") != "1":
        raise RuntimeError("Project-fact fairness downgrade requires a disposable database")
    _replace(_FIRST_PROJECT_FACT_TIER, _INCOMPLETE_PROJECT_TIER)
