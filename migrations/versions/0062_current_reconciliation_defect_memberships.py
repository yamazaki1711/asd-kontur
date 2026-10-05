"""Bind each reconciliation to its exact current defect versions.

Revision ID: 0062_current_defect_memberships
Revises: 0061_native_layout_locator_index
"""

from __future__ import annotations

import os

from alembic import op

revision = "0062_current_defect_memberships"
down_revision = "0061_native_layout_locator_index"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE workspace.project_reconciliation_defect_memberships (
          organization_id uuid NOT NULL,
          workspace_id uuid NOT NULL,
          reconciliation_id uuid NOT NULL,
          reconciliation_version bigint NOT NULL CHECK (reconciliation_version >= 1),
          member_sequence bigint NOT NULL CHECK (member_sequence >= 1),
          defect_id uuid NOT NULL,
          defect_version bigint NOT NULL CHECK (defect_version >= 1),
          membership_fingerprint text NOT NULL
            CHECK (membership_fingerprint ~ '^sha256:[a-f0-9]{64}$'),
          recorded_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
          PRIMARY KEY (
            organization_id,workspace_id,reconciliation_id,reconciliation_version,member_sequence
          ),
          UNIQUE (
            organization_id,workspace_id,reconciliation_id,reconciliation_version,
            defect_id,defect_version
          ),
          UNIQUE (organization_id,workspace_id,membership_fingerprint),
          FOREIGN KEY (
            organization_id,workspace_id,reconciliation_id,reconciliation_version
          ) REFERENCES workspace.project_understanding_reconciliations (
            organization_id,workspace_id,reconciliation_id,version
          ) ON DELETE RESTRICT,
          FOREIGN KEY (
            organization_id,workspace_id,defect_id,defect_version
          ) REFERENCES workspace.project_reconciliation_defects (
            organization_id,workspace_id,defect_id,version
          ) ON DELETE RESTRICT
        );
        ALTER TABLE workspace.project_reconciliation_defect_memberships
          ENABLE ROW LEVEL SECURITY;
        ALTER TABLE workspace.project_reconciliation_defect_memberships
          FORCE ROW LEVEL SECURITY;
        CREATE POLICY project_reconciliation_defect_memberships_scope
          ON workspace.project_reconciliation_defect_memberships
          USING (
            organization_id=NULLIF(current_setting('asd.organization_id',true),'')::uuid AND
            workspace_id=NULLIF(current_setting('asd.workspace_id',true),'')::uuid
          )
          WITH CHECK (
            organization_id=NULLIF(current_setting('asd.organization_id',true),'')::uuid AND
            workspace_id=NULLIF(current_setting('asd.workspace_id',true),'')::uuid
          );
        GRANT SELECT ON workspace.project_reconciliation_defect_memberships TO asd_app;
        GRANT SELECT,INSERT ON workspace.project_reconciliation_defect_memberships
          TO asd_document_worker;
        GRANT SELECT,DELETE ON workspace.project_reconciliation_defect_memberships
          TO asd_destruction_executor;
        CREATE TRIGGER project_reconciliation_defect_memberships_immutable
          BEFORE UPDATE OR DELETE
          ON workspace.project_reconciliation_defect_memberships
          FOR EACH ROW EXECUTE FUNCTION application.reject_spine_mutation_except_destruction();
        """
    )


def downgrade() -> None:
    if os.environ.get("ASD_ALLOW_DESTRUCTIVE_DOWNGRADE") != "1":
        raise RuntimeError("Defect membership downgrade requires a disposable database")
    op.execute("DROP TABLE workspace.project_reconciliation_defect_memberships")
