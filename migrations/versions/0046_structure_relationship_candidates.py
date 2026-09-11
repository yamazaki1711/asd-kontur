"""Persist evidence-bound structural relationship candidates.

Revision ID: 0046_structure_relationship_candidates
Revises: 0045_bounded_dep_recovery
"""

from __future__ import annotations

import os

from alembic import op

revision = "0046_structure_relationship_candidates"
down_revision = "0045_bounded_dep_recovery"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE workspace.project_structure_relationship_candidates (
            organization_id uuid NOT NULL,
            workspace_id uuid NOT NULL,
            relationship_candidate_id uuid NOT NULL,
            version bigint NOT NULL CHECK (version >= 1),
            relationship_kind text NOT NULL CHECK (relationship_kind IN
                ('contains','located_in','serves','connects_to','depends_on')),
            subject_raw_name text NOT NULL,
            subject_normalized_name text NOT NULL,
            object_raw_name text NOT NULL,
            object_normalized_name text NOT NULL,
            source_version_id uuid NOT NULL,
            source_locator_id uuid NOT NULL,
            status text NOT NULL CHECK (status IN ('candidate','confirmed','rejected','corrected')),
            candidate_digest text NOT NULL CHECK (candidate_digest ~ '^sha256:[a-f0-9]{64}$'),
            recorded_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (organization_id, workspace_id, relationship_candidate_id, version),
            FOREIGN KEY (organization_id, workspace_id, source_version_id)
                REFERENCES workspace.source_versions(organization_id, workspace_id, source_version_id)
                ON DELETE RESTRICT,
            FOREIGN KEY (organization_id, workspace_id, source_locator_id)
                REFERENCES workspace.source_locators(organization_id, workspace_id, source_locator_id)
                ON DELETE RESTRICT
        );
        CREATE INDEX project_structure_relationship_candidates_source_idx
          ON workspace.project_structure_relationship_candidates
          (organization_id, workspace_id, source_version_id, source_locator_id);
        ALTER TABLE workspace.project_structure_relationship_candidates ENABLE ROW LEVEL SECURITY;
        ALTER TABLE workspace.project_structure_relationship_candidates FORCE ROW LEVEL SECURITY;
        CREATE POLICY project_structure_relationship_candidates_scope
          ON workspace.project_structure_relationship_candidates
          USING (organization_id=NULLIF(current_setting('asd.organization_id',true),'')::uuid
             AND workspace_id=NULLIF(current_setting('asd.workspace_id',true),'')::uuid)
          WITH CHECK (organization_id=NULLIF(current_setting('asd.organization_id',true),'')::uuid
             AND workspace_id=NULLIF(current_setting('asd.workspace_id',true),'')::uuid);
        GRANT SELECT ON workspace.project_structure_relationship_candidates TO asd_app;
        GRANT SELECT, INSERT ON workspace.project_structure_relationship_candidates
          TO asd_document_worker;
        GRANT SELECT, DELETE ON workspace.project_structure_relationship_candidates
          TO asd_destruction_executor;
        CREATE TRIGGER project_structure_relationship_candidates_immutable
          BEFORE UPDATE OR DELETE ON workspace.project_structure_relationship_candidates
          FOR EACH ROW EXECUTE FUNCTION application.reject_spine_mutation_except_destruction();
        """
    )


def downgrade() -> None:
    if os.environ.get("ASD_ALLOW_DESTRUCTIVE_DOWNGRADE") != "1":
        raise RuntimeError("Relationship candidate downgrade requires a disposable database")
    op.execute("DROP TABLE workspace.project_structure_relationship_candidates")
