"""Persist bounded semantic dispositions for pit-like observations."""

from __future__ import annotations

import os

from alembic import op

revision = "0064_pit_observation_disposition_receipts"
down_revision = "0063_structure_group_receipts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE workspace.project_pit_observation_disposition_receipts (
          organization_id uuid NOT NULL,
          workspace_id uuid NOT NULL,
          group_fingerprint text NOT NULL
            CHECK (group_fingerprint ~ '^sha256:[a-f0-9]{64}$'),
          profile_version text NOT NULL
            CHECK (lower(profile_version) <> 'latest'),
          input_structure_node_ids uuid[] NOT NULL
            CHECK (cardinality(input_structure_node_ids) >= 1),
          input_manifest jsonb NOT NULL,
          outcome text NOT NULL CHECK (outcome IN ('accepted','failed')),
          decisions jsonb NOT NULL CHECK (jsonb_typeof(decisions) = 'array'),
          failure_code text,
          receipt_digest text NOT NULL CHECK (receipt_digest ~ '^sha256:[a-f0-9]{64}$'),
          recorded_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
          PRIMARY KEY (organization_id,workspace_id,group_fingerprint,profile_version),
          UNIQUE (organization_id,workspace_id,receipt_digest),
          CHECK (
            (outcome='accepted' AND failure_code IS NULL AND
             jsonb_array_length(decisions) = cardinality(input_structure_node_ids))
            OR (outcome='failed' AND failure_code IS NOT NULL AND
                jsonb_array_length(decisions) = 0)
          )
        );
        CREATE INDEX project_pit_observation_disposition_receipts_workspace_idx ON
          workspace.project_pit_observation_disposition_receipts
          (organization_id,workspace_id,profile_version,recorded_at);
        ALTER TABLE workspace.project_pit_observation_disposition_receipts
          ENABLE ROW LEVEL SECURITY;
        ALTER TABLE workspace.project_pit_observation_disposition_receipts
          FORCE ROW LEVEL SECURITY;
        CREATE POLICY project_pit_observation_disposition_receipts_scope
          ON workspace.project_pit_observation_disposition_receipts
          USING (
            organization_id=NULLIF(current_setting('asd.organization_id',true),'')::uuid AND
            workspace_id=NULLIF(current_setting('asd.workspace_id',true),'')::uuid
          )
          WITH CHECK (
            organization_id=NULLIF(current_setting('asd.organization_id',true),'')::uuid AND
            workspace_id=NULLIF(current_setting('asd.workspace_id',true),'')::uuid
          );
        GRANT SELECT ON workspace.project_pit_observation_disposition_receipts TO asd_app;
        GRANT SELECT,INSERT ON workspace.project_pit_observation_disposition_receipts
          TO asd_document_worker;
        GRANT SELECT,DELETE ON workspace.project_pit_observation_disposition_receipts
          TO asd_destruction_executor;
        CREATE TRIGGER project_pit_observation_disposition_receipts_immutable
          BEFORE UPDATE OR DELETE
          ON workspace.project_pit_observation_disposition_receipts
          FOR EACH ROW EXECUTE FUNCTION application.reject_spine_mutation_except_destruction();
        """
    )


def downgrade() -> None:
    if os.environ.get("ASD_ALLOW_DESTRUCTIVE_DOWNGRADE") != "1":
        raise RuntimeError("Pit observation disposition downgrade requires a disposable database")
    op.execute("DROP TABLE workspace.project_pit_observation_disposition_receipts")
