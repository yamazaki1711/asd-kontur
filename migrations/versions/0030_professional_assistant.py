"""Add durable, workspace-scoped professional assistant conversations.

Revision ID: 0030_professional_assistant
Revises: 0029_pilot_usable_e2e
Create Date: 2026-08-30
"""

from __future__ import annotations

import os

from alembic import op

revision = "0030_professional_assistant"
down_revision = "0029_pilot_usable_e2e"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE workspace.assistant_conversations (
          organization_id uuid NOT NULL,
          workspace_id uuid NOT NULL,
          conversation_id uuid NOT NULL,
          created_by_identity_id text NOT NULL,
          title text NOT NULL CHECK (length(title) BETWEEN 1 AND 160),
          created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
          PRIMARY KEY (organization_id,workspace_id,conversation_id),
          FOREIGN KEY (organization_id,workspace_id)
            REFERENCES workspace.workspaces(organization_id,workspace_id) ON DELETE RESTRICT
        );

        CREATE TABLE workspace.assistant_turns (
          organization_id uuid NOT NULL,
          workspace_id uuid NOT NULL,
          turn_id uuid NOT NULL,
          conversation_id uuid NOT NULL,
          turn_ordinal bigint NOT NULL CHECK (turn_ordinal >= 1),
          mode text NOT NULL CHECK (mode IN ('Tender','Support','Audit','Restoration')),
          question text NOT NULL CHECK (length(question) BETWEEN 2 AND 8000),
          requested_by_identity_id text NOT NULL,
          project_definition_id uuid,
          project_definition_version bigint,
          platform_memory_fingerprint text NOT NULL CHECK (
            platform_memory_fingerprint ~ '^sha256:[a-f0-9]{64}$'
          ),
          assistant_profile_version text NOT NULL CHECK (lower(assistant_profile_version)<>'latest'),
          model_profile_version text NOT NULL CHECK (lower(model_profile_version)<>'latest'),
          state text NOT NULL CHECK (state IN (
            'queued','leased','running','succeeded','failed','cancelled','reconciliation_required'
          )),
          attempt_count integer NOT NULL DEFAULT 0 CHECK (attempt_count >= 0),
          max_attempts integer NOT NULL DEFAULT 2 CHECK (max_attempts BETWEEN 1 AND 5),
          lease_owner text,
          lease_generation bigint NOT NULL DEFAULT 0 CHECK (lease_generation >= 0),
          lease_expires_at timestamptz,
          heartbeat_at timestamptz,
          cancellation_requested boolean NOT NULL DEFAULT false,
          failure_code text,
          request_digest text NOT NULL CHECK (request_digest ~ '^sha256:[a-f0-9]{64}$'),
          context_digest text CHECK (context_digest IS NULL OR context_digest ~ '^sha256:[a-f0-9]{64}$'),
          response_digest text CHECK (response_digest IS NULL OR response_digest ~ '^sha256:[a-f0-9]{64}$'),
          started_at timestamptz,
          completed_at timestamptz,
          created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
          PRIMARY KEY (organization_id,workspace_id,turn_id),
          UNIQUE (organization_id,workspace_id,conversation_id,turn_ordinal),
          UNIQUE (organization_id,workspace_id,request_digest),
          FOREIGN KEY (organization_id,workspace_id,conversation_id)
            REFERENCES workspace.assistant_conversations(
              organization_id,workspace_id,conversation_id
            ) ON DELETE RESTRICT,
          FOREIGN KEY (organization_id,workspace_id,project_definition_id,project_definition_version)
            REFERENCES workspace.project_definition_versions(
              organization_id,workspace_id,project_definition_id,version
            ) ON DELETE RESTRICT,
          CHECK ((project_definition_id IS NULL)=(project_definition_version IS NULL))
        );

        CREATE INDEX ix_assistant_turn_claim
          ON workspace.assistant_turns(state,created_at,turn_id)
          WHERE state='queued';

        CREATE TABLE workspace.assistant_turn_events (
          organization_id uuid NOT NULL,
          workspace_id uuid NOT NULL,
          turn_id uuid NOT NULL,
          event_sequence bigint NOT NULL CHECK (event_sequence >= 1),
          event_type text NOT NULL CHECK (event_type IN (
            'queued','leased','running','delta','source','completed','failed','cancelled',
            'reconciliation_required'
          )),
          public_payload jsonb NOT NULL,
          event_digest text NOT NULL CHECK (event_digest ~ '^sha256:[a-f0-9]{64}$'),
          recorded_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
          PRIMARY KEY (organization_id,workspace_id,turn_id,event_sequence),
          UNIQUE (organization_id,workspace_id,event_digest),
          FOREIGN KEY (organization_id,workspace_id,turn_id)
            REFERENCES workspace.assistant_turns(organization_id,workspace_id,turn_id)
            ON DELETE RESTRICT
        );

        CREATE TABLE workspace.assistant_messages (
          organization_id uuid NOT NULL,
          workspace_id uuid NOT NULL,
          message_id uuid NOT NULL,
          conversation_id uuid NOT NULL,
          message_ordinal bigint NOT NULL CHECK (message_ordinal >= 1),
          turn_id uuid NOT NULL,
          role text NOT NULL CHECK (role IN ('user','assistant')),
          content text NOT NULL CHECK (length(content) >= 1),
          sources jsonb NOT NULL DEFAULT '[]'::jsonb,
          action_proposals jsonb NOT NULL DEFAULT '[]'::jsonb,
          model_identity text,
          model_profile_version text,
          content_digest text NOT NULL CHECK (content_digest ~ '^sha256:[a-f0-9]{64}$'),
          created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
          PRIMARY KEY (organization_id,workspace_id,message_id),
          UNIQUE (organization_id,workspace_id,conversation_id,message_ordinal),
          UNIQUE (organization_id,workspace_id,turn_id,role),
          FOREIGN KEY (organization_id,workspace_id,conversation_id)
            REFERENCES workspace.assistant_conversations(
              organization_id,workspace_id,conversation_id
            ) ON DELETE RESTRICT,
          FOREIGN KEY (organization_id,workspace_id,turn_id)
            REFERENCES workspace.assistant_turns(organization_id,workspace_id,turn_id)
            ON DELETE RESTRICT
        );

        CREATE FUNCTION workspace.claim_next_assistant_turn(
          p_worker_identity text, p_lease_seconds integer
        ) RETURNS TABLE (
          organization_id uuid, workspace_id uuid, turn_id uuid, conversation_id uuid,
          mode text, question text, requested_by_identity_id text, attempt_number integer,
          lease_generation bigint
        ) LANGUAGE plpgsql SECURITY DEFINER
        SET search_path = pg_catalog, workspace
        AS $$
        DECLARE claimed workspace.assistant_turns%ROWTYPE; now_at timestamptz := clock_timestamp();
        BEGIN
          IF length(coalesce(p_worker_identity,'')) < 3 OR p_lease_seconds < 30 OR p_lease_seconds > 3600 THEN
            RAISE EXCEPTION 'invalid assistant lease request' USING ERRCODE='22023';
          END IF;
          UPDATE workspace.assistant_turns SET state='reconciliation_required',
            failure_code='assistant_worker_interrupted',completed_at=now_at,lease_owner=NULL,
            lease_expires_at=NULL
          WHERE state IN ('leased','running') AND lease_expires_at < now_at;
          SELECT * INTO claimed FROM workspace.assistant_turns
          WHERE state='queued' AND cancellation_requested=false
          ORDER BY created_at,turn_id FOR UPDATE SKIP LOCKED LIMIT 1;
          IF NOT FOUND THEN RETURN; END IF;
          UPDATE workspace.assistant_turns SET state='leased',
            attempt_count=attempt_count+1,lease_owner=p_worker_identity,
            lease_generation=workspace.assistant_turns.lease_generation+1,
            lease_expires_at=now_at+make_interval(secs=>p_lease_seconds),heartbeat_at=now_at,
            started_at=coalesce(started_at,now_at)
          WHERE workspace.assistant_turns.organization_id=claimed.organization_id
            AND workspace.assistant_turns.workspace_id=claimed.workspace_id
            AND workspace.assistant_turns.turn_id=claimed.turn_id;
          RETURN QUERY SELECT claimed.organization_id,claimed.workspace_id,claimed.turn_id,
            claimed.conversation_id,claimed.mode,claimed.question,claimed.requested_by_identity_id,
            claimed.attempt_count+1,claimed.lease_generation+1;
        END $$;
        REVOKE ALL ON FUNCTION workspace.claim_next_assistant_turn(text,integer) FROM PUBLIC;
        GRANT EXECUTE ON FUNCTION workspace.claim_next_assistant_turn(text,integer)
          TO asd_document_worker;
        """
    )
    tables = (
        "assistant_conversations",
        "assistant_turns",
        "assistant_turn_events",
        "assistant_messages",
    )
    for table in tables:
        op.execute(f"ALTER TABLE workspace.{table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE workspace.{table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY {table}_scope ON workspace.{table} USING ("
            "organization_id=NULLIF(current_setting('asd.organization_id',true),'')::uuid AND "
            "workspace_id=NULLIF(current_setting('asd.workspace_id',true),'')::uuid) WITH CHECK ("
            "organization_id=NULLIF(current_setting('asd.organization_id',true),'')::uuid AND "
            "workspace_id=NULLIF(current_setting('asd.workspace_id',true),'')::uuid)"
        )
        op.execute(f"GRANT SELECT,INSERT,UPDATE ON workspace.{table} TO asd_app")
        op.execute(f"GRANT SELECT,INSERT,UPDATE ON workspace.{table} TO asd_document_worker")
        op.execute(f"GRANT SELECT,DELETE ON workspace.{table} TO asd_destruction_executor")
    for table in ("assistant_conversations", "assistant_turn_events", "assistant_messages"):
        op.execute(
            f"CREATE TRIGGER {table}_immutable BEFORE UPDATE OR DELETE ON workspace.{table} "
            "FOR EACH ROW EXECUTE FUNCTION application.reject_spine_mutation_except_destruction()"
        )
    op.execute(
        "GRANT SELECT ON platform.practice_intelligence_units,"
        "platform.practice_intelligence_sources,platform.practice_intelligence_releases,"
        "platform.source_versions,platform.source_artifacts,platform.normative_provision_versions,"
        "platform.normative_editions,platform.normative_documents,platform.normative_artifacts "
        "TO asd_app"
    )


def downgrade() -> None:
    if os.environ.get("ASD_ALLOW_DESTRUCTIVE_DOWNGRADE") != "1":
        raise RuntimeError("Assistant downgrade requires a disposable database")
    op.execute("DROP FUNCTION workspace.claim_next_assistant_turn(text,integer)")
    op.execute("DROP TABLE workspace.assistant_messages")
    op.execute("DROP TABLE workspace.assistant_turn_events")
    op.execute("DROP TABLE workspace.assistant_turns")
    op.execute("DROP TABLE workspace.assistant_conversations")
