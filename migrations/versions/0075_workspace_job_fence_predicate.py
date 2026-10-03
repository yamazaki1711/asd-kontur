"""Expose a least-privilege workspace job-fence predicate.

Revision ID: 0075_workspace_job_fence_predicate
Revises: 0074_foreground_aware_job_claim
"""

from __future__ import annotations

import os

from alembic import op

revision = "0075_workspace_job_fence_predicate"
down_revision = "0074_foreground_aware_job_claim"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Let job producers inspect only the lifecycle write fence, not workspace rows."""

    op.execute(
        """
        CREATE FUNCTION workspace.workspace_accepts_durable_jobs(
          p_organization_id uuid,
          p_workspace_id uuid
        ) RETURNS boolean
        LANGUAGE sql STABLE SECURITY DEFINER
        SET search_path = pg_catalog, workspace
        AS $$
          SELECT EXISTS (
            SELECT 1
              FROM workspace.workspaces w
             WHERE w.organization_id=p_organization_id
               AND w.workspace_id=p_workspace_id
               AND w.lifecycle_state='ACTIVE'
               AND w.write_fenced=false
          )
        $$;
        REVOKE ALL ON FUNCTION workspace.workspace_accepts_durable_jobs(uuid,uuid) FROM PUBLIC;
        GRANT EXECUTE ON FUNCTION workspace.workspace_accepts_durable_jobs(uuid,uuid)
          TO asd_app, asd_document_worker;
        """
    )


def downgrade() -> None:
    if os.environ.get("ASD_ALLOW_DESTRUCTIVE_DOWNGRADE") != "1":
        raise RuntimeError("Workspace job-fence downgrade requires a disposable database")
    op.execute("DROP FUNCTION workspace.workspace_accepts_durable_jobs(uuid,uuid)")
