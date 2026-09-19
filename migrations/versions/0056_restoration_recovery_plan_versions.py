"""Persist immutable Restoration recovery-plan snapshots.

Revision ID: 0056_restoration_recovery_plan_versions
Revises: 0055_audit_delta_payloads
"""

from __future__ import annotations

import os

from alembic import op

revision = "0056_restoration_recovery_plan_versions"
down_revision = "0055_audit_delta_payloads"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE workspace.restoration_recovery_plan_versions (
          organization_id uuid NOT NULL,
          workspace_id uuid NOT NULL,
          recovery_process_id uuid NOT NULL,
          version bigint NOT NULL CHECK (version >= 1),
          state text NOT NULL CHECK (state IN ('partial','blocked')),
          basis_fingerprint text NOT NULL CHECK (basis_fingerprint ~ '^sha256:[a-f0-9]{64}$'),
          plan_fingerprint text NOT NULL CHECK (plan_fingerprint ~ '^sha256:[a-f0-9]{64}$'),
          plan jsonb NOT NULL,
          recorded_by_identity_id text NOT NULL,
          recorded_at timestamptz NOT NULL,
          PRIMARY KEY (organization_id,workspace_id,recovery_process_id,version),
          FOREIGN KEY (organization_id,workspace_id)
            REFERENCES workspace.workspaces(organization_id,workspace_id) ON DELETE RESTRICT,
          UNIQUE (organization_id,workspace_id,recovery_process_id,plan_fingerprint)
        );
        ALTER TABLE workspace.restoration_recovery_plan_versions ENABLE ROW LEVEL SECURITY;
        ALTER TABLE workspace.restoration_recovery_plan_versions FORCE ROW LEVEL SECURITY;
        CREATE POLICY restoration_recovery_plan_versions_app_scope
          ON workspace.restoration_recovery_plan_versions FOR ALL TO asd_app
          USING (
            organization_id = nullif(current_setting('asd.organization_id',true),'')::uuid
            AND workspace_id = nullif(current_setting('asd.workspace_id',true),'')::uuid
          ) WITH CHECK (
            organization_id = nullif(current_setting('asd.organization_id',true),'')::uuid
            AND workspace_id = nullif(current_setting('asd.workspace_id',true),'')::uuid
          );
        CREATE POLICY restoration_recovery_plan_versions_destruction_scope
          ON workspace.restoration_recovery_plan_versions FOR ALL TO asd_destruction_executor
          USING (
            organization_id = nullif(current_setting('asd.organization_id',true),'')::uuid
            AND workspace_id = nullif(current_setting('asd.workspace_id',true),'')::uuid
          ) WITH CHECK (
            organization_id = nullif(current_setting('asd.organization_id',true),'')::uuid
            AND workspace_id = nullif(current_setting('asd.workspace_id',true),'')::uuid
          );
        GRANT SELECT,INSERT ON workspace.restoration_recovery_plan_versions TO asd_app;
        GRANT SELECT,DELETE ON workspace.restoration_recovery_plan_versions TO asd_destruction_executor;
        CREATE TRIGGER restoration_recovery_plan_versions_immutable_guard
          BEFORE UPDATE OR DELETE ON workspace.restoration_recovery_plan_versions
          FOR EACH ROW EXECUTE FUNCTION application.reject_spine_mutation_except_destruction();
        """
    )


def downgrade() -> None:
    if os.environ.get("ASD_ALLOW_DESTRUCTIVE_DOWNGRADE") != "1":
        raise RuntimeError("Restoration recovery-plan downgrade requires a disposable database")
    op.execute("DROP TABLE workspace.restoration_recovery_plan_versions")
