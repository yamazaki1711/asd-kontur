"""Keep incomplete document intake ahead of historical deep re-analysis.

Revision ID: 0094_intake_before_fairness
Revises: 0093_relationship_schema_repair_v20
"""

from __future__ import annotations

import os

import sqlalchemy as sa
from alembic import op

revision = "0094_intake_before_fairness"
down_revision = "0093_relationship_schema_repair_v20"
branch_labels = None
depends_on = None

_LEGACY_PROCESSING_TIER = """CASE WHEN EXISTS (
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

_MODEL_SLOT_FAIRNESS = """COALESCE((
               SELECT max(served.started_at)
                 FROM workspace.durable_jobs served
                WHERE served.organization_id=j.organization_id
                  AND served.workspace_id=j.workspace_id
                  AND served.job_kind IN (
                    'OCR_EXTRACTION','DOCUMENT_PAGE_CLASSIFICATION',
                    'PROJECT_DEFINITION_EXTRACTION','WORK_QUANTITY_MATERIAL_EXTRACTION',
                    'PROJECT_STRUCTURE_RECONCILIATION','PROJECT_WORK_RECONCILIATION'
                  )
             ),'-infinity'::timestamptz) ASC"""

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
             ),1) ASC"""

_FAIRNESS_FIRST = f"""{_MODEL_SLOT_FAIRNESS},
             {_LEGACY_PROCESSING_TIER},
             j.priority DESC,j.created_at,j.job_id"""

_INTAKE_FIRST = f"""{_PROCESSING_TIER},
             {_SEMANTIC_COMPLETION_RATIO},
             {_MODEL_SLOT_FAIRNESS},
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
        raise RuntimeError("intake/fairness claim ordering unavailable")
    connection.execute(sa.text(definition.replace(source, target)))


def upgrade() -> None:
    """Finish incomplete source intake before fair-sharing historical analysis."""

    _replace_order(_FAIRNESS_FIRST, _INTAKE_FIRST)


def downgrade() -> None:
    if os.environ.get("ASD_ALLOW_DESTRUCTIVE_DOWNGRADE") != "1":
        raise RuntimeError("Intake-priority downgrade requires a disposable database")
    _replace_order(
        _INTAKE_FIRST,
        f"""{_MODEL_SLOT_FAIRNESS},
             {_LEGACY_PROCESSING_TIER},
             j.priority DESC,j.created_at,j.job_id""",
    )
