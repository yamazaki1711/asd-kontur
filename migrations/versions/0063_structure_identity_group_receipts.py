"""Persist terminal outcomes for bounded structure-identity groups.

Revision ID: 0063_structure_group_receipts
Revises: 0062_current_defect_memberships
"""

from __future__ import annotations

import os

from alembic import op

revision = "0063_structure_group_receipts"
down_revision = "0062_current_defect_memberships"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE workspace.project_structure_identity_group_receipts (
          organization_id uuid NOT NULL,
          workspace_id uuid NOT NULL,
          group_fingerprint text NOT NULL
            CHECK (group_fingerprint ~ '^sha256:[a-f0-9]{64}$'),
          reconciliation_profile_version text NOT NULL
            CHECK (lower(reconciliation_profile_version) <> 'latest'),
          input_structure_node_ids uuid[] NOT NULL
            CHECK (cardinality(input_structure_node_ids) >= 2),
          input_manifest jsonb NOT NULL,
          outcome text NOT NULL CHECK (outcome IN ('accepted','accepted_empty','failed')),
          identity_candidate_ids uuid[] NOT NULL DEFAULT ARRAY[]::uuid[],
          failure_code text,
          receipt_digest text NOT NULL CHECK (receipt_digest ~ '^sha256:[a-f0-9]{64}$'),
          recorded_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
          PRIMARY KEY (
            organization_id,workspace_id,group_fingerprint,reconciliation_profile_version
          ),
          UNIQUE (organization_id,workspace_id,receipt_digest),
          CHECK (
            (outcome='accepted' AND cardinality(identity_candidate_ids) >= 1 AND failure_code IS NULL)
            OR (outcome='accepted_empty' AND cardinality(identity_candidate_ids)=0 AND failure_code IS NULL)
            OR (outcome='failed' AND cardinality(identity_candidate_ids)=0 AND failure_code IS NOT NULL)
          )
        );
        CREATE INDEX project_structure_identity_group_receipts_workspace_idx ON
          workspace.project_structure_identity_group_receipts
          (organization_id,workspace_id,reconciliation_profile_version,recorded_at);
        ALTER TABLE workspace.project_structure_identity_group_receipts ENABLE ROW LEVEL SECURITY;
        ALTER TABLE workspace.project_structure_identity_group_receipts FORCE ROW LEVEL SECURITY;
        CREATE POLICY project_structure_identity_group_receipts_scope
          ON workspace.project_structure_identity_group_receipts
          USING (
            organization_id=NULLIF(current_setting('asd.organization_id',true),'')::uuid AND
            workspace_id=NULLIF(current_setting('asd.workspace_id',true),'')::uuid
          )
          WITH CHECK (
            organization_id=NULLIF(current_setting('asd.organization_id',true),'')::uuid AND
            workspace_id=NULLIF(current_setting('asd.workspace_id',true),'')::uuid
          );
        GRANT SELECT ON workspace.project_structure_identity_group_receipts TO asd_app;
        GRANT SELECT,INSERT ON workspace.project_structure_identity_group_receipts
          TO asd_document_worker;
        GRANT SELECT,DELETE ON workspace.project_structure_identity_group_receipts
          TO asd_destruction_executor;
        CREATE TRIGGER project_structure_identity_group_receipts_immutable
          BEFORE UPDATE OR DELETE
          ON workspace.project_structure_identity_group_receipts
          FOR EACH ROW EXECUTE FUNCTION application.reject_spine_mutation_except_destruction();
        """
    )


def downgrade() -> None:
    if os.environ.get("ASD_ALLOW_DESTRUCTIVE_DOWNGRADE") != "1":
        raise RuntimeError("Structure-group receipt downgrade requires a disposable database")
    op.execute("DROP TABLE workspace.project_structure_identity_group_receipts")
