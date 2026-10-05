"""Bind final Audit reports to exact immutable ActionRequest versions.

Revision ID: 0057_audit_report_action_request_memberships
Revises: 0056_restoration_recovery_plan_versions
"""

from __future__ import annotations

import os

from alembic import op

revision = "0057_audit_report_action_request_memberships"
down_revision = "0056_restoration_recovery_plan_versions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE workspace.audit_report_action_request_memberships (
          organization_id uuid NOT NULL,
          workspace_id uuid NOT NULL,
          audit_report_id uuid NOT NULL,
          audit_report_version bigint NOT NULL CHECK (audit_report_version >= 1),
          action_request_id uuid NOT NULL,
          action_request_version bigint NOT NULL CHECK (action_request_version >= 1),
          PRIMARY KEY (
            organization_id,workspace_id,audit_report_id,audit_report_version,
            action_request_id,action_request_version
          ),
          FOREIGN KEY (organization_id,workspace_id,audit_report_id,audit_report_version)
            REFERENCES workspace.audit_report_versions(
              organization_id,workspace_id,audit_report_id,version
            ) ON DELETE RESTRICT,
          FOREIGN KEY (organization_id,workspace_id,action_request_id,action_request_version)
            REFERENCES workspace.audit_action_request_versions(
              organization_id,workspace_id,action_request_id,version
            ) ON DELETE RESTRICT
        );
        ALTER TABLE workspace.audit_report_action_request_memberships ENABLE ROW LEVEL SECURITY;
        ALTER TABLE workspace.audit_report_action_request_memberships FORCE ROW LEVEL SECURITY;
        CREATE POLICY audit_report_action_request_memberships_audit_scope_policy
          ON workspace.audit_report_action_request_memberships FOR ALL TO asd_audit_service
          USING (
            organization_id = nullif(current_setting('asd.organization_id',true),'')::uuid
            AND workspace_id = nullif(current_setting('asd.workspace_id',true),'')::uuid
          ) WITH CHECK (
            organization_id = nullif(current_setting('asd.organization_id',true),'')::uuid
            AND workspace_id = nullif(current_setting('asd.workspace_id',true),'')::uuid
          );
        CREATE POLICY audit_report_action_request_memberships_destruction_scope_policy
          ON workspace.audit_report_action_request_memberships FOR ALL TO asd_destruction_executor
          USING (
            organization_id = nullif(current_setting('asd.organization_id',true),'')::uuid
            AND workspace_id = nullif(current_setting('asd.workspace_id',true),'')::uuid
          ) WITH CHECK (
            organization_id = nullif(current_setting('asd.organization_id',true),'')::uuid
            AND workspace_id = nullif(current_setting('asd.workspace_id',true),'')::uuid
          );
        GRANT SELECT,INSERT ON workspace.audit_report_action_request_memberships TO asd_audit_service;
        GRANT SELECT,DELETE ON workspace.audit_report_action_request_memberships TO asd_destruction_executor;
        CREATE TRIGGER audit_report_action_request_memberships_immutable_guard
          BEFORE UPDATE OR DELETE ON workspace.audit_report_action_request_memberships
          FOR EACH ROW EXECUTE FUNCTION workspace.reject_audit_version_mutation();
        CREATE OR REPLACE FUNCTION workspace.require_report_action_request_process()
        RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
          IF NOT EXISTS (
            SELECT 1
            FROM workspace.audit_report_versions report
            JOIN workspace.audit_action_request_versions request
              ON request.organization_id=report.organization_id
             AND request.workspace_id=report.workspace_id
             AND request.audit_process_id=report.audit_process_id
            WHERE report.organization_id=NEW.organization_id
              AND report.workspace_id=NEW.workspace_id
              AND report.audit_report_id=NEW.audit_report_id
              AND report.version=NEW.audit_report_version
              AND request.action_request_id=NEW.action_request_id
              AND request.version=NEW.action_request_version
          ) THEN
            RAISE EXCEPTION 'Audit report action request must belong to the same Audit process';
          END IF;
          RETURN NEW;
        END $$;
        CREATE TRIGGER audit_report_action_request_process_guard
          BEFORE INSERT ON workspace.audit_report_action_request_memberships
          FOR EACH ROW EXECUTE FUNCTION workspace.require_report_action_request_process();
        """
    )


def downgrade() -> None:
    if os.environ.get("ASD_ALLOW_DESTRUCTIVE_DOWNGRADE") != "1":
        raise RuntimeError(
            "Audit report-action membership downgrade requires a disposable database"
        )
    op.execute("DROP TABLE workspace.audit_report_action_request_memberships")
    op.execute("DROP FUNCTION IF EXISTS workspace.require_report_action_request_process()")
