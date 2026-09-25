"""Persist accepted bounded Qwen engineering-extraction batches.

Revision ID: 0039_engineering_batches
Revises: 0038_consultant_request_id
"""

from __future__ import annotations

import os

from alembic import op

revision = "0039_engineering_batches"
down_revision = "0038_consultant_request_id"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE workspace.engineering_extraction_batches (
            organization_id uuid NOT NULL,
            workspace_id uuid NOT NULL,
            source_version_id uuid NOT NULL,
            profile_version text NOT NULL CHECK (lower(profile_version) <> 'latest'),
            batch_ordinal bigint NOT NULL CHECK (batch_ordinal >= 1),
            batch_digest text NOT NULL CHECK (batch_digest ~ '^sha256:[a-f0-9]{64}$'),
            source_locator_ids uuid[] NOT NULL CHECK (cardinality(source_locator_ids) > 0),
            output_manifest jsonb NOT NULL,
            output_digest text NOT NULL CHECK (output_digest ~ '^sha256:[a-f0-9]{64}$'),
            terminal_status text NOT NULL CHECK (terminal_status IN ('accepted', 'failed')),
            typed_failure_code text,
            recorded_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (organization_id, workspace_id, source_version_id, profile_version, batch_digest),
            UNIQUE (organization_id, workspace_id, source_version_id, profile_version, batch_ordinal, batch_digest),
            FOREIGN KEY (organization_id, workspace_id, source_version_id)
                REFERENCES workspace.source_versions(organization_id, workspace_id, source_version_id)
                ON DELETE RESTRICT
        )
        """
    )
    op.execute(
        "CREATE INDEX engineering_extraction_batches_source_idx "
        "ON workspace.engineering_extraction_batches "
        "(organization_id, workspace_id, source_version_id, profile_version, batch_ordinal)"
    )
    op.execute("ALTER TABLE workspace.engineering_extraction_batches ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE workspace.engineering_extraction_batches FORCE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY engineering_extraction_batches_scope ON workspace.engineering_extraction_batches "
        "USING (organization_id=NULLIF(current_setting('asd.organization_id',true),'')::uuid AND "
        "workspace_id=NULLIF(current_setting('asd.workspace_id',true),'')::uuid) WITH CHECK "
        "(organization_id=NULLIF(current_setting('asd.organization_id',true),'')::uuid AND "
        "workspace_id=NULLIF(current_setting('asd.workspace_id',true),'')::uuid)"
    )
    op.execute("GRANT SELECT ON workspace.engineering_extraction_batches TO asd_app")
    op.execute(
        "GRANT SELECT, INSERT ON workspace.engineering_extraction_batches TO asd_document_worker"
    )
    op.execute(
        "GRANT SELECT, DELETE ON workspace.engineering_extraction_batches TO asd_destruction_executor"
    )
    op.execute(
        "CREATE TRIGGER engineering_extraction_batches_immutable BEFORE UPDATE OR DELETE ON "
        "workspace.engineering_extraction_batches FOR EACH ROW EXECUTE FUNCTION "
        "application.reject_spine_mutation_except_destruction()"
    )


def downgrade() -> None:
    if os.environ.get("ASD_ALLOW_DESTRUCTIVE_DOWNGRADE") != "1":
        raise RuntimeError("Engineering extraction batch downgrade requires a disposable database")
    op.execute("DROP TABLE workspace.engineering_extraction_batches")
