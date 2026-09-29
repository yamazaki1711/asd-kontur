"""Expose bounded active-project scopes to the autonomous orchestrator.

Revision ID: 0076_autonomous_project_orchestration
Revises: 0075_workspace_job_fence_predicate
"""

from __future__ import annotations

import os

from alembic import op

revision = "0076_autonomous_project_orchestration"
down_revision = "0075_workspace_job_fence_predicate"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE FUNCTION workspace.autonomous_project_processing_scopes(p_limit integer)
        RETURNS TABLE (
          organization_id uuid,
          workspace_id uuid,
          owner_identity_id text,
          last_progress_at timestamptz
        )
        LANGUAGE plpgsql SECURITY DEFINER
        SET search_path = pg_catalog, workspace
        AS $$
        BEGIN
          IF p_limit < 1 OR p_limit > 64 THEN
            RAISE EXCEPTION 'invalid autonomous project scope limit' USING ERRCODE='22023';
          END IF;
          RETURN QUERY
          SELECT jobs.organization_id,jobs.workspace_id,
                 (array_agg(jobs.created_by_identity_id ORDER BY jobs.created_at DESC))[1],
                 max(COALESCE(jobs.completed_at,jobs.heartbeat_at,jobs.started_at,jobs.created_at))
            FROM workspace.durable_jobs jobs
            JOIN workspace.workspaces active
              ON active.organization_id=jobs.organization_id
             AND active.workspace_id=jobs.workspace_id
             AND active.lifecycle_state='ACTIVE'
             AND active.write_fenced=false
           WHERE jobs.job_kind IN (
             'DOCUMENT_ADMISSION','DOCUMENT_FORMAT_INVENTORY','PDF_PAGE_HEALTH_ANALYSIS',
             'NATIVE_LAYOUT_EXTRACTION','OCR_ROUTING','OCR_EXTRACTION',
             'DOCUMENT_PAGE_CLASSIFICATION','DOCUMENT_AGGREGATION',
             'PROJECT_DEFINITION_EXTRACTION','WORK_QUANTITY_MATERIAL_EXTRACTION',
             'WORK_PACKAGE_ASSEMBLY','REQUIREMENT_MATRIX_ASSEMBLY',
             'PROJECT_UNDERSTANDING_RECONCILIATION','PROJECT_STRUCTURE_RECONCILIATION',
             'PROJECT_WORK_RECONCILIATION'
           )
           GROUP BY jobs.organization_id,jobs.workspace_id
           ORDER BY max(COALESCE(jobs.completed_at,jobs.heartbeat_at,jobs.started_at,jobs.created_at)) DESC,
                    jobs.organization_id,jobs.workspace_id
           LIMIT p_limit;
        END $$;
        REVOKE ALL ON FUNCTION workspace.autonomous_project_processing_scopes(integer) FROM PUBLIC;
        GRANT EXECUTE ON FUNCTION workspace.autonomous_project_processing_scopes(integer)
          TO asd_document_worker;
        """
    )


def downgrade() -> None:
    if os.environ.get("ASD_ALLOW_DESTRUCTIVE_DOWNGRADE") != "1":
        raise RuntimeError("Autonomous project orchestration downgrade requires a disposable database")
    op.execute("DROP FUNCTION workspace.autonomous_project_processing_scopes(integer)")
