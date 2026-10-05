"""Bind each reconciliation to its exact current work-package versions.

Revision ID: 0060_current_package_memberships
Revises: 0059_scoped_worker_job_claims
"""

from __future__ import annotations

import os

from alembic import op

revision = "0060_current_package_memberships"
down_revision = "0059_scoped_worker_job_claims"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "GRANT SELECT ON platform.work_types,platform.work_type_versions TO asd_document_worker"
    )
    op.execute(
        """
        CREATE TABLE workspace.project_reconciliation_work_package_memberships (
          organization_id uuid NOT NULL,
          workspace_id uuid NOT NULL,
          reconciliation_id uuid NOT NULL,
          reconciliation_version bigint NOT NULL CHECK (reconciliation_version >= 1),
          member_sequence bigint NOT NULL CHECK (member_sequence >= 1),
          work_package_id uuid NOT NULL,
          work_package_version bigint NOT NULL CHECK (work_package_version >= 1),
          membership_fingerprint text NOT NULL
            CHECK (membership_fingerprint ~ '^sha256:[a-f0-9]{64}$'),
          recorded_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
          PRIMARY KEY (
            organization_id,workspace_id,reconciliation_id,reconciliation_version,member_sequence
          ),
          UNIQUE (
            organization_id,workspace_id,reconciliation_id,reconciliation_version,
            work_package_id,work_package_version
          ),
          UNIQUE (organization_id,workspace_id,membership_fingerprint),
          FOREIGN KEY (
            organization_id,workspace_id,reconciliation_id,reconciliation_version
          ) REFERENCES workspace.project_understanding_reconciliations (
            organization_id,workspace_id,reconciliation_id,version
          ) ON DELETE RESTRICT,
          FOREIGN KEY (
            organization_id,workspace_id,work_package_id,work_package_version
          ) REFERENCES workspace.construction_work_package_versions (
            organization_id,workspace_id,work_package_id,version
          ) ON DELETE RESTRICT
        );
        ALTER TABLE workspace.project_reconciliation_work_package_memberships
          ENABLE ROW LEVEL SECURITY;
        ALTER TABLE workspace.project_reconciliation_work_package_memberships
          FORCE ROW LEVEL SECURITY;
        CREATE POLICY project_reconciliation_work_package_memberships_scope
          ON workspace.project_reconciliation_work_package_memberships
          USING (
            organization_id=NULLIF(current_setting('asd.organization_id',true),'')::uuid AND
            workspace_id=NULLIF(current_setting('asd.workspace_id',true),'')::uuid
          )
          WITH CHECK (
            organization_id=NULLIF(current_setting('asd.organization_id',true),'')::uuid AND
            workspace_id=NULLIF(current_setting('asd.workspace_id',true),'')::uuid
          );
        GRANT SELECT ON workspace.project_reconciliation_work_package_memberships TO asd_app;
        GRANT SELECT,INSERT ON workspace.project_reconciliation_work_package_memberships
          TO asd_document_worker;
        GRANT SELECT,DELETE ON workspace.project_reconciliation_work_package_memberships
          TO asd_destruction_executor;
        CREATE TRIGGER project_reconciliation_work_package_memberships_immutable
          BEFORE UPDATE OR DELETE
          ON workspace.project_reconciliation_work_package_memberships
          FOR EACH ROW EXECUTE FUNCTION application.reject_spine_mutation_except_destruction();
        """
    )


def downgrade() -> None:
    if os.environ.get("ASD_ALLOW_DESTRUCTIVE_DOWNGRADE") != "1":
        raise RuntimeError("Work-package membership downgrade requires a disposable database")
    op.execute("DROP TABLE workspace.project_reconciliation_work_package_memberships")
    op.execute(
        "REVOKE SELECT ON platform.work_types,platform.work_type_versions FROM asd_document_worker"
    )
