"""Make dependency-recovery replay safe with pre-existing recovery jobs.

Revision ID: 0044_dependency_recovery_idempotency
Revises: 0043_engineering_v5
"""

from __future__ import annotations

import os

from alembic import op

revision = "0044_dep_recovery_idempotency"
down_revision = "0043_engineering_v5"
branch_labels = None
depends_on = None

_IDEMPOTENCY_CONSTRAINT = "durable_jobs_organization_id_workspace_id_job_kind_idempote_key"


def upgrade() -> None:
    op.execute(
        "ALTER FUNCTION workspace.recover_dependency_terminal_failures() "
        "RENAME TO recover_dependency_terminal_failures_v1"
    )
    op.execute(
        f"""
        CREATE FUNCTION workspace.recover_dependency_terminal_failures()
        RETURNS integer
        LANGUAGE plpgsql SECURITY DEFINER
        SET search_path = pg_catalog, workspace
        AS $$
        DECLARE
          violated_constraint text;
        BEGIN
          RETURN workspace.recover_dependency_terminal_failures_v1();
        EXCEPTION WHEN unique_violation THEN
          GET STACKED DIAGNOSTICS violated_constraint = CONSTRAINT_NAME;
          IF violated_constraint = '{_IDEMPOTENCY_CONSTRAINT}' THEN
            RETURN 0;
          END IF;
          RAISE;
        END $$;
        REVOKE ALL ON FUNCTION workspace.recover_dependency_terminal_failures() FROM PUBLIC;
        GRANT EXECUTE ON FUNCTION workspace.recover_dependency_terminal_failures()
          TO asd_document_worker;
        """
    )


def downgrade() -> None:
    if os.environ.get("ASD_ALLOW_DESTRUCTIVE_DOWNGRADE") != "1":
        raise RuntimeError("Dependency recovery downgrade requires a disposable database")
    op.execute("DROP FUNCTION workspace.recover_dependency_terminal_failures()")
    op.execute(
        "ALTER FUNCTION workspace.recover_dependency_terminal_failures_v1() "
        "RENAME TO recover_dependency_terminal_failures"
    )
