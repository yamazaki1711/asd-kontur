"""Add append-only intake archive lineage and project candidate review decisions.

Revision ID: 0028_industrial_intake
Revises: 0027_public_deployment
Create Date: 2026-08-28
"""

from __future__ import annotations

import os

from alembic import op

revision = "0028_industrial_intake"
down_revision = "0027_public_deployment"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("GRANT USAGE ON SCHEMA projection TO asd_document_worker")
    op.execute(
        "ALTER TABLE workspace.document_processing_states DROP CONSTRAINT "
        "document_processing_states_admission_status_check"
    )
    op.execute(
        "ALTER TABLE workspace.document_processing_states ADD CONSTRAINT "
        "document_processing_states_admission_status_check CHECK "
        "(admission_status IN "
        "('pending','accepted','rejected','quarantined','reconciliation_required'))"
    )
    op.execute("ALTER TABLE workspace.durable_jobs DROP CONSTRAINT durable_jobs_state_check")
    op.execute(
        "ALTER TABLE workspace.durable_jobs ADD CONSTRAINT durable_jobs_state_check CHECK "
        "(state IN ('queued','paused','leased','running','succeeded','failed','cancelled',"
        "'reconciliation_required'))"
    )
    op.execute(
        """
        CREATE TABLE workspace.intake_archive_members (
          organization_id uuid NOT NULL,
          workspace_id uuid NOT NULL,
          archive_document_id uuid NOT NULL,
          archive_document_version bigint NOT NULL CHECK (archive_document_version >= 1),
          member_ordinal bigint NOT NULL CHECK (member_ordinal >= 1),
          member_document_id uuid NOT NULL,
          member_document_version bigint NOT NULL CHECK (member_document_version >= 1),
          member_relative_path text NOT NULL,
          member_content_digest text NOT NULL CHECK (member_content_digest ~ '^sha256:[a-f0-9]{64}$'),
          uncompressed_size_bytes bigint NOT NULL CHECK (uncompressed_size_bytes > 0),
          lineage_digest text NOT NULL CHECK (lineage_digest ~ '^sha256:[a-f0-9]{64}$'),
          recorded_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
          PRIMARY KEY (
            organization_id, workspace_id, archive_document_id,
            archive_document_version, member_ordinal
          ),
          UNIQUE (organization_id, workspace_id, lineage_digest),
          FOREIGN KEY (organization_id,workspace_id,archive_document_id,archive_document_version)
            REFERENCES workspace.document_versions(organization_id,workspace_id,document_id,version)
            ON DELETE RESTRICT,
          FOREIGN KEY (organization_id,workspace_id,member_document_id,member_document_version)
            REFERENCES workspace.document_versions(organization_id,workspace_id,document_id,version)
            ON DELETE RESTRICT
        );

        CREATE TABLE workspace.project_candidate_review_decisions (
          organization_id uuid NOT NULL,
          workspace_id uuid NOT NULL,
          review_decision_id uuid NOT NULL,
          decision_version bigint NOT NULL CHECK (decision_version >= 1),
          candidate_kind text NOT NULL CHECK (
            candidate_kind IN ('project_field','work_type','quantity','material')
          ),
          candidate_id uuid NOT NULL,
          candidate_version bigint NOT NULL CHECK (candidate_version >= 1),
          source_version_id uuid NOT NULL,
          source_locator_id uuid NOT NULL,
          action text NOT NULL CHECK (action IN ('confirmed','rejected','corrected')),
          original_value jsonb NOT NULL,
          resolved_value jsonb,
          reason text NOT NULL CHECK (length(reason) BETWEEN 3 AND 1000),
          supersedes_decision_version bigint,
          decided_by_identity_id text NOT NULL,
          decision_digest text NOT NULL CHECK (decision_digest ~ '^sha256:[a-f0-9]{64}$'),
          decided_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
          PRIMARY KEY (organization_id,workspace_id,review_decision_id,decision_version),
          UNIQUE (organization_id,workspace_id,decision_digest),
          FOREIGN KEY (organization_id,workspace_id,source_version_id)
            REFERENCES workspace.source_versions(organization_id,workspace_id,source_version_id)
            ON DELETE RESTRICT,
          FOREIGN KEY (organization_id,workspace_id,source_locator_id)
            REFERENCES workspace.source_locators(organization_id,workspace_id,source_locator_id)
            ON DELETE RESTRICT,
          CHECK ((action='corrected')=(resolved_value IS NOT NULL))
        );

        CREATE TABLE workspace.job_control_decisions (
          organization_id uuid NOT NULL,
          workspace_id uuid NOT NULL,
          control_decision_id uuid NOT NULL,
          job_id uuid NOT NULL,
          action text NOT NULL CHECK (action IN ('pause','resume','manual_retry')),
          prior_state text NOT NULL,
          result_state text NOT NULL,
          derived_job_id uuid,
          decided_by_identity_id text NOT NULL,
          decision_digest text NOT NULL CHECK (decision_digest ~ '^sha256:[a-f0-9]{64}$'),
          decided_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
          PRIMARY KEY (organization_id,workspace_id,control_decision_id),
          UNIQUE (organization_id,workspace_id,decision_digest),
          FOREIGN KEY (organization_id,workspace_id,job_id)
            REFERENCES workspace.durable_jobs(organization_id,workspace_id,job_id)
            ON DELETE RESTRICT,
          FOREIGN KEY (organization_id,workspace_id,derived_job_id)
            REFERENCES workspace.durable_jobs(organization_id,workspace_id,job_id)
            ON DELETE RESTRICT
        );
        """
    )
    for table in (
        "intake_archive_members",
        "project_candidate_review_decisions",
        "job_control_decisions",
    ):
        op.execute(f"ALTER TABLE workspace.{table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE workspace.{table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY {table}_scope ON workspace.{table} USING ("
            "organization_id=NULLIF(current_setting('asd.organization_id',true),'')::uuid AND "
            "workspace_id=NULLIF(current_setting('asd.workspace_id',true),'')::uuid) WITH CHECK ("
            "organization_id=NULLIF(current_setting('asd.organization_id',true),'')::uuid AND "
            "workspace_id=NULLIF(current_setting('asd.workspace_id',true),'')::uuid)"
        )
        op.execute(f"GRANT SELECT,INSERT ON workspace.{table} TO asd_app")
        op.execute(f"GRANT SELECT,INSERT ON workspace.{table} TO asd_document_worker")
        op.execute(f"GRANT SELECT,DELETE ON workspace.{table} TO asd_destruction_executor")
        op.execute(
            f"CREATE TRIGGER {table}_immutable BEFORE UPDATE OR DELETE ON workspace.{table} "
            "FOR EACH ROW EXECUTE FUNCTION application.reject_spine_mutation_except_destruction()"
        )


def downgrade() -> None:
    if os.environ.get("ASD_ALLOW_DESTRUCTIVE_DOWNGRADE") != "1":
        raise RuntimeError("Industrial intake downgrade requires a disposable database")
    op.execute("REVOKE USAGE ON SCHEMA projection FROM asd_document_worker")
    op.execute("DROP TABLE workspace.job_control_decisions")
    op.execute("DROP TABLE workspace.project_candidate_review_decisions")
    op.execute("DROP TABLE workspace.intake_archive_members")
    op.execute(
        "ALTER TABLE workspace.document_processing_states DROP CONSTRAINT "
        "document_processing_states_admission_status_check"
    )
    op.execute(
        "ALTER TABLE workspace.document_processing_states ADD CONSTRAINT "
        "document_processing_states_admission_status_check CHECK "
        "(admission_status IN ('pending','accepted','rejected','reconciliation_required'))"
    )
    op.execute("ALTER TABLE workspace.durable_jobs DROP CONSTRAINT durable_jobs_state_check")
    op.execute(
        "ALTER TABLE workspace.durable_jobs ADD CONSTRAINT durable_jobs_state_check CHECK "
        "(state IN ('queued','leased','running','succeeded','failed','cancelled',"
        "'reconciliation_required'))"
    )
