"""Add auditable multi-step professional-assistant reasoning receipts.

Revision ID: 0031_assistant_reasoning
Revises: 0030_professional_assistant
Create Date: 2026-08-30
"""

from __future__ import annotations

import os

from alembic import op

revision = "0031_assistant_reasoning"
down_revision = "0030_professional_assistant"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE workspace.assistant_tool_receipts (
          organization_id uuid NOT NULL,
          workspace_id uuid NOT NULL,
          turn_id uuid NOT NULL,
          step_sequence integer NOT NULL CHECK (step_sequence BETWEEN 1 AND 4),
          tool_name text NOT NULL CHECK (tool_name LIKE 'consultant.%'),
          request_payload jsonb NOT NULL,
          planning_reason text NOT NULL CHECK (length(planning_reason) BETWEEN 1 AND 500),
          terminal_outcome text NOT NULL CHECK (terminal_outcome IN ('found','not_found','blocked')),
          response_digest text NOT NULL CHECK (response_digest ~ '^sha256:[a-f0-9]{64}$'),
          source_ids jsonb NOT NULL DEFAULT '[]'::jsonb,
          recorded_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
          PRIMARY KEY (organization_id,workspace_id,turn_id,step_sequence),
          FOREIGN KEY (organization_id,workspace_id,turn_id)
            REFERENCES workspace.assistant_turns(organization_id,workspace_id,turn_id)
            ON DELETE RESTRICT
        );

        CREATE TABLE workspace.assistant_quality_receipts (
          organization_id uuid NOT NULL,
          workspace_id uuid NOT NULL,
          turn_id uuid NOT NULL,
          logical_profile text NOT NULL,
          model_profile text NOT NULL,
          planning_profile text NOT NULL,
          synthesis_profile text NOT NULL,
          validation_profile text NOT NULL,
          intent text NOT NULL CHECK (intent IN ('general_engineering','normative','workspace','mixed','clarification_required')),
          answer_type text NOT NULL,
          deterministic_checks jsonb NOT NULL,
          model_checks jsonb NOT NULL,
          passed boolean NOT NULL,
          receipt_fingerprint text NOT NULL CHECK (receipt_fingerprint ~ '^sha256:[a-f0-9]{64}$'),
          recorded_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
          PRIMARY KEY (organization_id,workspace_id,turn_id),
          FOREIGN KEY (organization_id,workspace_id,turn_id)
            REFERENCES workspace.assistant_turns(organization_id,workspace_id,turn_id)
            ON DELETE RESTRICT
        );

        CREATE TABLE workspace.assistant_dialogue_state_versions (
          organization_id uuid NOT NULL,
          workspace_id uuid NOT NULL,
          conversation_id uuid NOT NULL,
          version bigint NOT NULL CHECK (version >= 1),
          source_turn_id uuid NOT NULL,
          summary text NOT NULL CHECK (length(summary) BETWEEN 1 AND 1000),
          active_subjects jsonb NOT NULL DEFAULT '[]'::jsonb,
          state_fingerprint text NOT NULL CHECK (state_fingerprint ~ '^sha256:[a-f0-9]{64}$'),
          recorded_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
          PRIMARY KEY (organization_id,workspace_id,conversation_id,version),
          FOREIGN KEY (organization_id,workspace_id,conversation_id)
            REFERENCES workspace.assistant_conversations(organization_id,workspace_id,conversation_id)
            ON DELETE RESTRICT,
          FOREIGN KEY (organization_id,workspace_id,source_turn_id)
            REFERENCES workspace.assistant_turns(organization_id,workspace_id,turn_id)
            ON DELETE RESTRICT
        );

        CREATE TABLE application.construction_consultant_quality_decisions (
          decision_id uuid NOT NULL,
          version bigint NOT NULL CHECK (version >= 1),
          status text NOT NULL CHECK (status IN ('pending','quality_ready','blocked')),
          source_commit text NOT NULL CHECK (source_commit ~ '^[a-f0-9]{40}$'),
          matrix_receipt_digest text NOT NULL CHECK (matrix_receipt_digest ~ '^sha256:[a-f0-9]{64}$'),
          external_receipt_digest text CHECK (
            external_receipt_digest IS NULL OR external_receipt_digest ~ '^sha256:[a-f0-9]{64}$'
          ),
          criteria jsonb NOT NULL,
          blockers jsonb NOT NULL DEFAULT '[]'::jsonb,
          decision_fingerprint text NOT NULL CHECK (decision_fingerprint ~ '^sha256:[a-f0-9]{64}$'),
          recorded_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
          PRIMARY KEY (decision_id,version)
        );
        """
    )
    workspace_tables = (
        "assistant_tool_receipts",
        "assistant_quality_receipts",
        "assistant_dialogue_state_versions",
    )
    for table in workspace_tables:
        op.execute(f"ALTER TABLE workspace.{table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE workspace.{table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY {table}_scope ON workspace.{table} USING ("
            "organization_id=NULLIF(current_setting('asd.organization_id',true),'')::uuid AND "
            "workspace_id=NULLIF(current_setting('asd.workspace_id',true),'')::uuid) WITH CHECK ("
            "organization_id=NULLIF(current_setting('asd.organization_id',true),'')::uuid AND "
            "workspace_id=NULLIF(current_setting('asd.workspace_id',true),'')::uuid)"
        )
        op.execute(f"GRANT SELECT ON workspace.{table} TO asd_app")
        op.execute(f"GRANT SELECT,INSERT ON workspace.{table} TO asd_document_worker")
        op.execute(f"GRANT SELECT,DELETE ON workspace.{table} TO asd_destruction_executor")
        op.execute(
            f"CREATE TRIGGER {table}_immutable BEFORE UPDATE OR DELETE ON workspace.{table} "
            "FOR EACH ROW EXECUTE FUNCTION application.reject_spine_mutation_except_destruction()"
        )
    op.execute(
        "CREATE TRIGGER construction_consultant_quality_decisions_immutable BEFORE UPDATE OR DELETE "
        "ON application.construction_consultant_quality_decisions FOR EACH ROW EXECUTE FUNCTION "
        "application.reject_spine_mutation_except_destruction()"
    )
    op.execute(
        "GRANT SELECT ON application.construction_consultant_quality_decisions TO asd_app,asd_document_worker"
    )


def downgrade() -> None:
    if os.environ.get("ASD_ALLOW_DESTRUCTIVE_DOWNGRADE") != "1":
        raise RuntimeError("Assistant reasoning downgrade requires a disposable database")
    op.execute("DROP TABLE application.construction_consultant_quality_decisions")
    op.execute("DROP TABLE workspace.assistant_dialogue_state_versions")
    op.execute("DROP TABLE workspace.assistant_quality_receipts")
    op.execute("DROP TABLE workspace.assistant_tool_receipts")
