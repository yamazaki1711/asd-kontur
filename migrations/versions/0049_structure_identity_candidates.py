"""Persist evidence-bound candidate identity groups across source observations.

Revision ID: 0049_structure_identity_candidates
Revises: 0048_incremental_reconciliation_claim_priority
"""

from __future__ import annotations

import os

from alembic import op

revision = "0049_structure_identity_candidates"
down_revision = "0048_incremental_reconciliation_claim_priority"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE workspace.project_structure_identity_candidates (
            organization_id uuid NOT NULL,
            workspace_id uuid NOT NULL,
            identity_candidate_id uuid NOT NULL,
            version bigint NOT NULL CHECK (version >= 1),
            identity_kind text NOT NULL CHECK (identity_kind IN
                ('local_area','facility','excavation_pit','structure','zone')),
            canonical_label text NOT NULL,
            member_structure_node_ids uuid[] NOT NULL
                CHECK (cardinality(member_structure_node_ids) >= 2),
            source_locator_ids uuid[] NOT NULL
                CHECK (cardinality(source_locator_ids) >= 2),
            confidence numeric NOT NULL CHECK (confidence >= 0 AND confidence <= 1),
            status text NOT NULL CHECK (status IN ('candidate','confirmed','rejected','corrected')),
            reconciliation_profile_version text NOT NULL
                CHECK (lower(reconciliation_profile_version) <> 'latest'),
            candidate_digest text NOT NULL CHECK (candidate_digest ~ '^sha256:[a-f0-9]{64}$'),
            recorded_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (organization_id, workspace_id, identity_candidate_id, version),
            UNIQUE (organization_id, workspace_id, candidate_digest)
        );
        CREATE INDEX project_structure_identity_candidates_workspace_idx ON
          workspace.project_structure_identity_candidates
          (organization_id, workspace_id, reconciliation_profile_version, recorded_at);
        ALTER TABLE workspace.project_structure_identity_candidates ENABLE ROW LEVEL SECURITY;
        ALTER TABLE workspace.project_structure_identity_candidates FORCE ROW LEVEL SECURITY;
        CREATE POLICY project_structure_identity_candidates_scope
          ON workspace.project_structure_identity_candidates
          USING (organization_id=NULLIF(current_setting('asd.organization_id',true),'')::uuid
             AND workspace_id=NULLIF(current_setting('asd.workspace_id',true),'')::uuid)
          WITH CHECK (organization_id=NULLIF(current_setting('asd.organization_id',true),'')::uuid
             AND workspace_id=NULLIF(current_setting('asd.workspace_id',true),'')::uuid);
        GRANT SELECT ON workspace.project_structure_identity_candidates TO asd_app;
        GRANT SELECT, INSERT ON workspace.project_structure_identity_candidates
          TO asd_document_worker;
        GRANT SELECT, DELETE ON workspace.project_structure_identity_candidates
          TO asd_destruction_executor;
        CREATE TRIGGER project_structure_identity_candidates_immutable
          BEFORE UPDATE OR DELETE ON workspace.project_structure_identity_candidates
          FOR EACH ROW EXECUTE FUNCTION application.reject_spine_mutation_except_destruction();
        """
    )


def downgrade() -> None:
    if os.environ.get("ASD_ALLOW_DESTRUCTIVE_DOWNGRADE") != "1":
        raise RuntimeError("Identity-candidate downgrade requires a disposable database")
    op.execute("DROP TABLE workspace.project_structure_identity_candidates")
