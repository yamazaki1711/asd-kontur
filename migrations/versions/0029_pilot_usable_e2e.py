"""Add immutable pilot results, reviews, exports and readiness decisions.

Revision ID: 0029_pilot_usable_e2e
Revises: 0028_industrial_intake
Create Date: 2026-08-30
"""

from __future__ import annotations

import os

from alembic import op

revision = "0029_pilot_usable_e2e"
down_revision = "0028_industrial_intake"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE workspace.pilot_mode_result_versions (
          organization_id uuid NOT NULL,
          workspace_id uuid NOT NULL,
          result_id uuid NOT NULL,
          version bigint NOT NULL CHECK (version >= 1),
          mode text NOT NULL CHECK (mode IN ('Tender','Support','Audit','Restoration')),
          project_definition_id uuid,
          project_definition_version bigint,
          matrix_id uuid,
          matrix_version bigint,
          result_payload jsonb NOT NULL,
          source_manifest jsonb NOT NULL,
          unresolved_questions jsonb NOT NULL,
          status text NOT NULL CHECK (status IN ('draft_with_open_questions','reviewed_draft')),
          result_fingerprint text NOT NULL CHECK (result_fingerprint ~ '^sha256:[a-f0-9]{64}$'),
          formed_by_identity_id text NOT NULL,
          formed_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
          PRIMARY KEY (organization_id,workspace_id,result_id,version),
          UNIQUE (organization_id,workspace_id,result_fingerprint),
          FOREIGN KEY (organization_id,workspace_id,project_definition_id,project_definition_version)
            REFERENCES workspace.project_definition_versions(
              organization_id,workspace_id,project_definition_id,version
            ) ON DELETE RESTRICT,
          FOREIGN KEY (organization_id,workspace_id,matrix_id,matrix_version)
            REFERENCES workspace.work_requirement_matrix_versions(
              organization_id,workspace_id,matrix_id,version
            ) ON DELETE RESTRICT,
          CHECK ((project_definition_id IS NULL)=(project_definition_version IS NULL)),
          CHECK ((matrix_id IS NULL)=(matrix_version IS NULL))
        );

        CREATE TABLE workspace.pilot_result_item_decisions (
          organization_id uuid NOT NULL,
          workspace_id uuid NOT NULL,
          decision_id uuid NOT NULL,
          decision_version bigint NOT NULL CHECK (decision_version >= 1),
          result_id uuid NOT NULL,
          result_version bigint NOT NULL CHECK (result_version >= 1),
          item_id uuid NOT NULL,
          item_version bigint NOT NULL CHECK (item_version >= 1),
          action text NOT NULL CHECK (
            action IN ('accepted','corrected','excluded','status_changed','commented')
          ),
          original_payload jsonb NOT NULL,
          resolved_fields jsonb,
          comment text NOT NULL CHECK (length(comment) BETWEEN 3 AND 2000),
          supersedes_decision_version bigint,
          decided_by_identity_id text NOT NULL,
          decision_digest text NOT NULL CHECK (decision_digest ~ '^sha256:[a-f0-9]{64}$'),
          decided_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
          PRIMARY KEY (organization_id,workspace_id,decision_id,decision_version),
          UNIQUE (organization_id,workspace_id,decision_digest),
          FOREIGN KEY (organization_id,workspace_id,result_id,result_version)
            REFERENCES workspace.pilot_mode_result_versions(
              organization_id,workspace_id,result_id,version
            ) ON DELETE RESTRICT,
          CHECK ((action IN ('corrected','status_changed'))=(resolved_fields IS NOT NULL))
        );

        CREATE TABLE workspace.pilot_export_versions (
          organization_id uuid NOT NULL,
          workspace_id uuid NOT NULL,
          export_id uuid NOT NULL,
          version bigint NOT NULL CHECK (version >= 1),
          result_id uuid NOT NULL,
          result_version bigint NOT NULL CHECK (result_version >= 1),
          export_kind text NOT NULL CHECK (export_kind IN (
            'disagreement_protocol','contract_changes','requirement_matrix','id_package',
            'register','audit_report','recovery_plan','recovered_drafts','workspace_results'
          )),
          output_format text NOT NULL CHECK (output_format IN ('docx','pdf','zip')),
          object_key text NOT NULL,
          media_type text NOT NULL,
          size_bytes bigint NOT NULL CHECK (size_bytes > 0),
          content_digest text NOT NULL CHECK (content_digest ~ '^sha256:[a-f0-9]{64}$'),
          source_manifest jsonb NOT NULL,
          unresolved_questions jsonb NOT NULL,
          export_fingerprint text NOT NULL CHECK (export_fingerprint ~ '^sha256:[a-f0-9]{64}$'),
          created_by_identity_id text NOT NULL,
          created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
          PRIMARY KEY (organization_id,workspace_id,export_id,version),
          UNIQUE (organization_id,workspace_id,export_fingerprint),
          FOREIGN KEY (organization_id,workspace_id,result_id,result_version)
            REFERENCES workspace.pilot_mode_result_versions(
              organization_id,workspace_id,result_id,version
            ) ON DELETE RESTRICT
        );

        CREATE TABLE application.trial_readiness_decisions (
          decision_id uuid NOT NULL,
          version bigint NOT NULL CHECK (version >= 1),
          deployed_commit text NOT NULL CHECK (deployed_commit ~ '^[a-f0-9]{40}$'),
          status text NOT NULL CHECK (status IN ('trial_ready','blocked')),
          criteria jsonb NOT NULL,
          pilot_thresholds jsonb NOT NULL,
          external_receipts jsonb NOT NULL,
          user_blockers jsonb NOT NULL,
          rollback_target text NOT NULL,
          decision_fingerprint text NOT NULL CHECK (decision_fingerprint ~ '^sha256:[a-f0-9]{64}$'),
          decided_by_identity_id text NOT NULL,
          decided_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
          PRIMARY KEY (decision_id,version),
          UNIQUE (decision_fingerprint)
        );
        """
    )
    for table in (
        "pilot_mode_result_versions",
        "pilot_result_item_decisions",
        "pilot_export_versions",
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
    op.execute("GRANT SELECT,INSERT ON application.trial_readiness_decisions TO asd_app")
    op.execute(
        "CREATE TRIGGER trial_readiness_decisions_immutable BEFORE UPDATE OR DELETE ON "
        "application.trial_readiness_decisions FOR EACH ROW EXECUTE FUNCTION "
        "platform.reject_immutable_mutation()"
    )


def downgrade() -> None:
    if os.environ.get("ASD_ALLOW_DESTRUCTIVE_DOWNGRADE") != "1":
        raise RuntimeError("Pilot workflow downgrade requires a disposable database")
    op.execute("DROP TABLE application.trial_readiness_decisions")
    op.execute("DROP TABLE workspace.pilot_export_versions")
    op.execute("DROP TABLE workspace.pilot_result_item_decisions")
    op.execute("DROP TABLE workspace.pilot_mode_result_versions")
