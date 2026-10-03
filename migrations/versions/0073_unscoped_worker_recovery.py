"""Expose bounded recovery scopes to the shared document worker.

Revision ID: 0073_unscoped_worker_recovery
Revises: 0072_commercial_work_reconciliation_profile
"""

from __future__ import annotations

import os

from alembic import op

revision = "0073_unscoped_worker_recovery"
down_revision = "0072_commercial_work_reconciliation_profile"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE FUNCTION workspace.expired_exhausted_job_scopes(p_limit integer)
        RETURNS TABLE (organization_id uuid, workspace_id uuid)
        LANGUAGE plpgsql SECURITY DEFINER
        SET search_path = pg_catalog, workspace
        AS $$
        BEGIN
          IF p_limit < 1 OR p_limit > 64 THEN
            RAISE EXCEPTION 'invalid expired job scope limit' USING ERRCODE='22023';
          END IF;
          RETURN QUERY
          SELECT jobs.organization_id,jobs.workspace_id
            FROM workspace.durable_jobs jobs
           WHERE jobs.state IN ('leased','running')
             AND jobs.lease_expires_at < clock_timestamp()
             AND (jobs.attempt_count >= jobs.max_attempts
                  OR jobs.cancellation_state='requested')
           GROUP BY jobs.organization_id,jobs.workspace_id
           ORDER BY min(jobs.lease_expires_at),jobs.organization_id,jobs.workspace_id
           LIMIT p_limit;
        END $$;
        REVOKE ALL ON FUNCTION workspace.expired_exhausted_job_scopes(integer) FROM PUBLIC;
        GRANT EXECUTE ON FUNCTION workspace.expired_exhausted_job_scopes(integer)
          TO asd_document_worker;

        CREATE FUNCTION workspace.idle_project_work_reconciliation_scopes(p_limit integer)
        RETURNS TABLE (organization_id uuid, workspace_id uuid)
        LANGUAGE plpgsql SECURITY DEFINER
        SET search_path = pg_catalog, workspace
        AS $$
        BEGIN
          IF p_limit < 1 OR p_limit > 64 THEN
            RAISE EXCEPTION 'invalid project work refill scope limit' USING ERRCODE='22023';
          END IF;
          RETURN QUERY
          SELECT jobs.organization_id,jobs.workspace_id
            FROM workspace.durable_jobs jobs
           WHERE jobs.job_kind='PROJECT_WORK_RECONCILIATION'
           GROUP BY jobs.organization_id,jobs.workspace_id
          HAVING count(*) FILTER (WHERE jobs.state IN ('queued','leased','running'))=0
           ORDER BY max(jobs.created_at) DESC,jobs.organization_id,jobs.workspace_id
           LIMIT p_limit;
        END $$;
        REVOKE ALL ON FUNCTION workspace.idle_project_work_reconciliation_scopes(integer)
          FROM PUBLIC;
        GRANT EXECUTE ON FUNCTION workspace.idle_project_work_reconciliation_scopes(integer)
          TO asd_document_worker;
        """
    )


def downgrade() -> None:
    if os.environ.get("ASD_ALLOW_DESTRUCTIVE_DOWNGRADE") != "1":
        raise RuntimeError("Unscoped worker recovery downgrade requires a disposable database")
    op.execute(
        "DROP FUNCTION workspace.idle_project_work_reconciliation_scopes(integer);"
        "DROP FUNCTION workspace.expired_exhausted_job_scopes(integer)"
    )
