from __future__ import annotations

import os

from alembic import op

revision = "0037_construction_consultant"
down_revision = "0036_ntd_search_binding"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE platform.construction_consultant_conversations (
            organization_id uuid NOT NULL,
            conversation_id uuid NOT NULL,
            created_by_identity_id text NOT NULL,
            title text NOT NULL CHECK (length(title) BETWEEN 1 AND 160),
            created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (organization_id, conversation_id)
        )
        """
    )

    op.execute(
        """
        CREATE TABLE platform.construction_consultant_messages (
            organization_id uuid NOT NULL,
            message_id uuid NOT NULL,
            conversation_id uuid NOT NULL,
            message_ordinal bigint NOT NULL CHECK (message_ordinal >= 1),
            role text NOT NULL CHECK (role IN ('user', 'assistant')),
            content text NOT NULL CHECK (length(content) >= 1),
            sources jsonb NOT NULL DEFAULT '[]'::jsonb,
            model_identity text,
            model_profile_version text,
            content_digest text NOT NULL CHECK (content_digest ~ '^sha256:[a-f0-9]{64}$'),
            created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (organization_id, message_id),
            UNIQUE (organization_id, conversation_id, message_ordinal),
            FOREIGN KEY (organization_id, conversation_id)
                REFERENCES platform.construction_consultant_conversations (organization_id, conversation_id)
                ON DELETE RESTRICT
        )
        """
    )

    for table in [
        "construction_consultant_conversations",
        "construction_consultant_messages",
    ]:
        op.execute(f"ALTER TABLE platform.{table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE platform.{table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY {table}_scope ON platform.{table} USING ("
            "organization_id=NULLIF(current_setting('asd.organization_id',true),'')::uuid) WITH CHECK ("
            "organization_id=NULLIF(current_setting('asd.organization_id',true),'')::uuid)"
        )
        op.execute(f"GRANT SELECT, INSERT, UPDATE ON platform.{table} TO asd_app")
        op.execute(f"GRANT SELECT, INSERT, UPDATE ON platform.{table} TO asd_document_worker")
        op.execute(f"GRANT SELECT, DELETE ON platform.{table} TO asd_destruction_executor")
        op.execute(
            f"CREATE TRIGGER {table}_reject_spine_mutation "
            "BEFORE UPDATE OR DELETE ON platform."
            f"{table} FOR EACH ROW EXECUTE FUNCTION application.reject_spine_mutation_except_destruction()"
        )


def downgrade() -> None:
    if os.environ.get("ASD_ALLOW_DESTRUCTIVE_DOWNGRADE") != "1":
        raise RuntimeError("Assistant downgrade requires a disposable database")
    op.execute("DROP TABLE platform.construction_consultant_messages")
    op.execute("DROP TABLE platform.construction_consultant_conversations")
