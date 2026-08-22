"""Create the G-04 persistence and authorization foundation.

Revision ID: 0001_g04
Revises: None
Create Date: 2026-08-23
"""

from __future__ import annotations

import os

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0001_g04"
down_revision = None
branch_labels = None
depends_on = None

SCHEMAS = ("platform", "organization", "workspace", "audit", "messaging")

CONTRACT_SCHEMAS = (
    (
        "urn:asd-kontur:contracts:v0.1:schema:common",
        "sha256:3fa97be7e48471e5da1b30fdb4df50cc549f457239267f6fd3bd69b52464717e",
    ),
    (
        "urn:asd-kontur:contracts:v0.1:schema:error",
        "sha256:52525a0edbee2909ca32a0de948e297d0765cfff1e806f3aea581193112b92c0",
    ),
    (
        "urn:asd-kontur:contracts:v0.1:schema:message",
        "sha256:3125699d93d9de504810b08e23bbabe8a711fbef1e1bef8dadbe7a1fedc7395b",
    ),
    (
        "urn:asd-kontur:contracts:v0.1:schema:source-evidence",
        "sha256:a24830cbc469e9da213086380cb94518b053df1a25f12f4029680e8f9ddfbf4f",
    ),
    (
        "urn:asd-kontur:contracts:v0.1:schema:candidate-fact",
        "sha256:dab0978b7025168e02d2e6d454140029b41c6a023d8ef505485b9dc4871acc6c",
    ),
    (
        "urn:asd-kontur:contracts:v0.1:schema:rules-knowledge",
        "sha256:97b34d94eb187d6c87baeb30464180161643e192b40f18042f74a1fef279c798",
    ),
    (
        "urn:asd-kontur:contracts:v0.1:schema:vlm-execution",
        "sha256:e4e15429405c43469e9ec8172b882c4df1dcd834707e9dbe11d5bd3feef54b65",
    ),
    (
        "urn:asd-kontur:contracts:v0.1:schema:storage-sync",
        "sha256:7c2933bc2ed3ae2931aaacdd4fe437c6c50762e60995bd13726ba8bb6cdd5a52",
    ),
    (
        "urn:asd-kontur:contracts:v0.1:schema:lifecycle",
        "sha256:9a1c9b7be7222e00dbf074a68d2d251bb5eecb1ada21ba80f7589c463ca396e8",
    ),
    (
        "urn:asd-kontur:contracts:v0.1:schema:authorization-audit",
        "sha256:a7a9fcd076949d5b11338a8b4226b37973c5080f3f26549d396b228a0076c63f",
    ),
    (
        "urn:asd-kontur:contracts:v0.1:schema:generation",
        "sha256:9e5a399e9ba34179dd85f7454f540e3e9ea2c913c799c271e10b5ef8156af6ed",
    ),
    (
        "urn:asd-kontur:contracts:v0.1:schema:geometry",
        "sha256:aa2ae281d53c4f5b4aeaf3ec7a67bd7bf72544138e5399c323469727cedbd1a5",
    ),
    (
        "urn:asd-kontur:contracts:v0.1:schema:mode-deliverable",
        "sha256:ee8ac8472ee134072c9db19adde1c2ad535b968fcfeb4cbb6a1122a4376098bc",
    ),
)


def upgrade() -> None:
    op.execute(
        "DO $$ BEGIN "
        "IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'asd_app') THEN "
        "CREATE ROLE asd_app NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT; "
        "END IF; END $$"
    )
    for schema in SCHEMAS:
        op.execute(sa.schema.CreateSchema(schema, if_not_exists=True))
    _create_platform_contract_registry()
    _create_organization_scope()
    _create_workspace_scope()
    _create_audit()
    _create_messaging()
    _apply_rls_and_grants()


def _create_platform_contract_registry() -> None:
    table = op.create_table(
        "contract_schema_versions",
        sa.Column("schema_id", sa.Text(), primary_key=True),
        sa.Column("schema_version", sa.Text(), primary_key=True),
        sa.Column("fingerprint", sa.Text(), nullable=False, unique=True),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column(
            "installed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "lower(schema_version) <> 'latest'", name="ck_contract_schema_exact_version"
        ),
        sa.CheckConstraint(
            "fingerprint ~ '^sha256:[a-f0-9]{64}$'", name="ck_contract_schema_fingerprint"
        ),
        schema="platform",
    )
    op.bulk_insert(
        table,
        [
            {
                "schema_id": schema_id,
                "schema_version": "0.1.0",
                "fingerprint": digest,
                "status": "accepted",
            }
            for schema_id, digest in CONTRACT_SCHEMAS
        ],
    )


def _create_organization_scope() -> None:
    op.create_table(
        "organizations",
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("display_name", sa.Text(), nullable=False),
        sa.Column("external_id", sa.Text()),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("revision", sa.BigInteger(), nullable=False),
        sa.Column("retention_class", sa.Text(), nullable=False),
        sa.Column("created_by_identity_id", sa.Text(), nullable=False),
        sa.Column("correlation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint("revision >= 1", name="ck_organization_revision_positive"),
        sa.CheckConstraint(
            "status IN ('active', 'suspended', 'closed')", name="ck_organization_status"
        ),
        schema="organization",
    )
    op.create_table(
        "construction_objects",
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("construction_object_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("display_name", sa.Text(), nullable=False),
        sa.Column("external_id", sa.Text()),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("revision", sa.BigInteger(), nullable=False),
        sa.Column("retention_class", sa.Text(), nullable=False),
        sa.Column("created_by_identity_id", sa.Text(), nullable=False),
        sa.Column("correlation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organization.organizations.organization_id"],
            ondelete="RESTRICT",
            name="fk_construction_object_organization",
        ),
        sa.UniqueConstraint(
            "organization_id", "external_id", name="uq_construction_object_external_id"
        ),
        sa.CheckConstraint("revision >= 1", name="ck_construction_object_revision_positive"),
        schema="organization",
    )


def _create_workspace_scope() -> None:
    op.create_table(
        "workspaces",
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("construction_object_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("lifecycle_state", sa.Text(), nullable=False),
        sa.Column("revision", sa.BigInteger(), nullable=False),
        sa.Column("retention_class", sa.Text(), nullable=False),
        sa.Column("retention_profile_key", sa.Text(), nullable=False),
        sa.Column("retention_profile_version", sa.Text(), nullable=False),
        sa.Column("policy_assignment_key", sa.Text(), nullable=False),
        sa.Column("policy_assignment_version", sa.Text(), nullable=False),
        sa.Column("rule_set_key", sa.Text(), nullable=False),
        sa.Column("rule_set_version", sa.Text(), nullable=False),
        sa.Column("contract_registry_version", sa.Text(), nullable=False),
        sa.Column("created_by_identity_id", sa.Text(), nullable=False),
        sa.Column("correlation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "construction_object_id"],
            [
                "organization.construction_objects.organization_id",
                "organization.construction_objects.construction_object_id",
            ],
            ondelete="RESTRICT",
            name="fk_workspace_construction_object",
        ),
        sa.CheckConstraint("revision >= 1", name="ck_workspace_revision_positive"),
        sa.CheckConstraint(
            "lifecycle_state IN ('provisioned', 'active', 'frozen', 'finalized', 'archived', 'blocked')",
            name="ck_workspace_lifecycle_state",
        ),
        sa.CheckConstraint(
            "lower(retention_profile_version) <> 'latest' AND lower(policy_assignment_version) <> 'latest' AND lower(rule_set_version) <> 'latest' AND lower(contract_registry_version) <> 'latest'",
            name="ck_workspace_exact_versions",
        ),
        schema="workspace",
    )
    op.create_table(
        "workspace_revisions",
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("revision", sa.BigInteger(), primary_key=True),
        sa.Column(
            "workspace_version_id", postgresql.UUID(as_uuid=True), nullable=False, unique=True
        ),
        sa.Column("lifecycle_state", sa.Text(), nullable=False),
        sa.Column("reason_code", sa.Text(), nullable=False),
        sa.Column("retention_profile_key", sa.Text(), nullable=False),
        sa.Column("retention_profile_version", sa.Text(), nullable=False),
        sa.Column("policy_assignment_key", sa.Text(), nullable=False),
        sa.Column("policy_assignment_version", sa.Text(), nullable=False),
        sa.Column("rule_set_key", sa.Text(), nullable=False),
        sa.Column("rule_set_version", sa.Text(), nullable=False),
        sa.Column("contract_registry_version", sa.Text(), nullable=False),
        sa.Column("inventory_fingerprint", sa.Text()),
        sa.Column("created_by_identity_id", sa.Text(), nullable=False),
        sa.Column("correlation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("causation_id", postgresql.UUID(as_uuid=True)),
        sa.Column(
            "recorded_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "workspace_id"],
            ["workspace.workspaces.organization_id", "workspace.workspaces.workspace_id"],
            ondelete="RESTRICT",
            name="fk_workspace_revision_workspace",
        ),
        sa.CheckConstraint("revision >= 1", name="ck_workspace_version_revision_positive"),
        schema="workspace",
    )
    op.create_table(
        "mode_executions",
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("mode_execution_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("mode", sa.Text(), nullable=False),
        sa.Column("purpose", sa.Text(), nullable=False),
        sa.Column("state", sa.Text(), nullable=False),
        sa.Column("revision", sa.BigInteger(), nullable=False),
        sa.Column("input_manifest_ref", sa.Text(), nullable=False),
        sa.Column("contract_key", sa.Text(), nullable=False),
        sa.Column("contract_version", sa.Text(), nullable=False),
        sa.Column("schema_id", sa.Text(), nullable=False),
        sa.Column("schema_version", sa.Text(), nullable=False),
        sa.Column("policy_assignment_key", sa.Text(), nullable=False),
        sa.Column("policy_assignment_version", sa.Text(), nullable=False),
        sa.Column("rule_set_key", sa.Text(), nullable=False),
        sa.Column("rule_set_version", sa.Text(), nullable=False),
        sa.Column("retention_class", sa.Text(), nullable=False),
        sa.Column("created_by_identity_id", sa.Text(), nullable=False),
        sa.Column("correlation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("causation_id", postgresql.UUID(as_uuid=True)),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "workspace_id"],
            ["workspace.workspaces.organization_id", "workspace.workspaces.workspace_id"],
            ondelete="RESTRICT",
            name="fk_mode_execution_workspace",
        ),
        sa.CheckConstraint(
            "mode IN ('Tender', 'Support', 'Audit', 'Restoration')", name="ck_mode_execution_mode"
        ),
        sa.CheckConstraint(
            "state IN ('requested', 'running', 'blocked', 'completed', 'failed', 'cancelled')",
            name="ck_mode_execution_state",
        ),
        sa.CheckConstraint("revision >= 1", name="ck_mode_execution_revision_positive"),
        sa.CheckConstraint(
            "lower(contract_version) <> 'latest' AND lower(schema_version) <> 'latest' AND lower(policy_assignment_version) <> 'latest' AND lower(rule_set_version) <> 'latest'",
            name="ck_mode_execution_exact_versions",
        ),
        schema="workspace",
    )
    op.create_table(
        "objects",
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("object_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("object_version", sa.BigInteger(), nullable=False),
        sa.Column("object_class", sa.Text(), nullable=False),
        sa.Column("content_digest", sa.Text(), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("media_type", sa.Text(), nullable=False),
        sa.Column("storage_adapter_key", sa.Text(), nullable=False),
        sa.Column("storage_receipt_ref", sa.Text(), nullable=False),
        sa.Column("access_capability_ref", sa.Text(), nullable=False),
        sa.Column("classification", sa.Text(), nullable=False),
        sa.Column("retention_class", sa.Text(), nullable=False),
        sa.Column("created_by_identity_id", sa.Text(), nullable=False),
        sa.Column("correlation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "workspace_id"],
            ["workspace.workspaces.organization_id", "workspace.workspaces.workspace_id"],
            ondelete="RESTRICT",
            name="fk_workspace_object_workspace",
        ),
        sa.UniqueConstraint(
            "organization_id",
            "workspace_id",
            "object_id",
            "object_version",
            name="uq_workspace_object_version",
        ),
        sa.CheckConstraint("object_version >= 1", name="ck_workspace_object_version_positive"),
        sa.CheckConstraint("size_bytes >= 0", name="ck_workspace_object_size_nonnegative"),
        sa.CheckConstraint(
            "content_digest ~ '^sha256:[a-f0-9]{64}$'", name="ck_workspace_object_digest"
        ),
        schema="workspace",
    )
    op.create_table(
        "object_links",
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("link_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("source_object_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("target_object_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("relation_kind", sa.Text(), nullable=False),
        sa.Column("created_by_identity_id", sa.Text(), nullable=False),
        sa.Column("correlation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "workspace_id", "source_object_id"],
            [
                "workspace.objects.organization_id",
                "workspace.objects.workspace_id",
                "workspace.objects.object_id",
            ],
            ondelete="RESTRICT",
            name="fk_object_link_source_same_workspace",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "workspace_id", "target_object_id"],
            [
                "workspace.objects.organization_id",
                "workspace.objects.workspace_id",
                "workspace.objects.object_id",
            ],
            ondelete="RESTRICT",
            name="fk_object_link_target_same_workspace",
        ),
        schema="workspace",
    )


def _create_audit() -> None:
    op.create_table(
        "workspace_records",
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("audit_record_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("audit_version", sa.Integer(), nullable=False),
        sa.Column(
            "recorded_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column("actor_identity_id", sa.Text()),
        sa.Column("service_identity_id", sa.Text()),
        sa.Column("capability", sa.Text(), nullable=False),
        sa.Column("operation", sa.Text(), nullable=False),
        sa.Column("outcome_code", sa.Text(), nullable=False),
        sa.Column("contract_key", sa.Text(), nullable=False),
        sa.Column("contract_version", sa.Text(), nullable=False),
        sa.Column("policy_key", sa.Text(), nullable=False),
        sa.Column("policy_version", sa.Text(), nullable=False),
        sa.Column("correlation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("causation_id", postgresql.UUID(as_uuid=True)),
        sa.Column("safe_message_key", sa.Text(), nullable=False),
        sa.Column("diagnostic_reference", sa.Text()),
        sa.Column("retention_class", sa.Text(), nullable=False),
        sa.Column("record_digest", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id", "workspace_id"],
            ["workspace.workspaces.organization_id", "workspace.workspaces.workspace_id"],
            ondelete="RESTRICT",
            name="fk_audit_workspace",
        ),
        sa.CheckConstraint(
            "actor_identity_id IS NOT NULL OR service_identity_id IS NOT NULL",
            name="ck_audit_actor_or_service",
        ),
        sa.CheckConstraint("lower(contract_version) <> 'latest'", name="ck_audit_contract_exact"),
        sa.CheckConstraint("lower(policy_version) <> 'latest'", name="ck_audit_policy_exact"),
        sa.CheckConstraint(
            "record_digest ~ '^sha256:[a-f0-9]{64}$'", name="ck_audit_record_digest"
        ),
        schema="audit",
    )
    op.execute(
        "CREATE FUNCTION audit.reject_mutation() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'audit records are append-only' USING ERRCODE = '55000'; END $$"
    )
    op.execute(
        "CREATE TRIGGER workspace_audit_no_update BEFORE UPDATE ON audit.workspace_records FOR EACH ROW EXECUTE FUNCTION audit.reject_mutation()"
    )
    op.execute(
        "CREATE TRIGGER workspace_audit_no_delete BEFORE DELETE ON audit.workspace_records FOR EACH ROW EXECUTE FUNCTION audit.reject_mutation()"
    )


def _create_messaging() -> None:
    op.create_table(
        "workspace_outbox",
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("outbox_record_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("event_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("aggregate_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("aggregate_version", sa.BigInteger(), nullable=False),
        sa.Column("destination", sa.Text(), nullable=False),
        sa.Column("state", sa.Text(), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("contract_key", sa.Text(), nullable=False),
        sa.Column("contract_version", sa.Text(), nullable=False),
        sa.Column("schema_id", sa.Text(), nullable=False),
        sa.Column("schema_version", sa.Text(), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("payload_digest", sa.Text(), nullable=False),
        sa.Column("retention_class", sa.Text(), nullable=False),
        sa.Column("correlation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("causation_id", postgresql.UUID(as_uuid=True)),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "workspace_id"],
            ["workspace.workspaces.organization_id", "workspace.workspaces.workspace_id"],
            ondelete="RESTRICT",
            name="fk_outbox_workspace",
        ),
        sa.UniqueConstraint("organization_id", "workspace_id", "event_id", name="uq_outbox_event"),
        sa.CheckConstraint("attempt_count >= 0", name="ck_outbox_attempt_nonnegative"),
        sa.CheckConstraint(
            "lower(contract_version) <> 'latest' AND lower(schema_version) <> 'latest'",
            name="ck_outbox_exact_versions",
        ),
        schema="messaging",
    )
    op.create_index(
        "ix_workspace_outbox_pending",
        "workspace_outbox",
        ["organization_id", "workspace_id", "state", "created_at"],
        schema="messaging",
    )
    op.create_table(
        "workspace_inbox_receipts",
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("consumer_key", sa.Text(), primary_key=True),
        sa.Column("message_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("payload_digest", sa.Text(), nullable=False),
        sa.Column("outcome", sa.Text(), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("contract_key", sa.Text(), nullable=False),
        sa.Column("contract_version", sa.Text(), nullable=False),
        sa.Column("schema_id", sa.Text(), nullable=False),
        sa.Column("schema_version", sa.Text(), nullable=False),
        sa.Column("correlation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "received_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "workspace_id"],
            ["workspace.workspaces.organization_id", "workspace.workspaces.workspace_id"],
            ondelete="RESTRICT",
            name="fk_inbox_workspace",
        ),
        sa.CheckConstraint("attempt_count >= 1", name="ck_inbox_attempt_positive"),
        sa.CheckConstraint(
            "lower(contract_version) <> 'latest' AND lower(schema_version) <> 'latest'",
            name="ck_inbox_exact_versions",
        ),
        schema="messaging",
    )
    op.create_table(
        "workspace_idempotency",
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("handler_key", sa.Text(), primary_key=True),
        sa.Column("idempotency_key", sa.Text(), primary_key=True),
        sa.Column("semantic_digest", sa.Text(), nullable=False),
        sa.Column("command_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("state", sa.Text(), nullable=False),
        sa.Column("outcome_ref", sa.Text()),
        sa.Column("correlation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.ForeignKeyConstraint(
            ["organization_id", "workspace_id"],
            ["workspace.workspaces.organization_id", "workspace.workspaces.workspace_id"],
            ondelete="RESTRICT",
            name="fk_idempotency_workspace",
        ),
        sa.CheckConstraint(
            "semantic_digest ~ '^sha256:[a-f0-9]{64}$'", name="ck_idempotency_digest"
        ),
        schema="messaging",
    )


def _apply_rls_and_grants() -> None:
    op.execute(
        "GRANT USAGE ON SCHEMA platform, organization, workspace, audit, messaging TO asd_app"
    )
    op.execute("GRANT SELECT ON platform.contract_schema_versions TO asd_app")
    op.execute(
        "GRANT SELECT, INSERT, UPDATE ON organization.organizations, organization.construction_objects TO asd_app"
    )
    op.execute(
        "GRANT SELECT, INSERT, UPDATE ON workspace.workspaces, workspace.workspace_revisions, workspace.mode_executions, workspace.objects, workspace.object_links TO asd_app"
    )
    op.execute("GRANT SELECT, INSERT ON audit.workspace_records TO asd_app")
    op.execute("REVOKE UPDATE, DELETE, TRUNCATE ON audit.workspace_records FROM asd_app")
    op.execute(
        "GRANT SELECT, INSERT, UPDATE ON messaging.workspace_outbox, messaging.workspace_inbox_receipts, messaging.workspace_idempotency TO asd_app"
    )
    organization_tables = ("organizations", "construction_objects")
    workspace_tables = (
        "workspaces",
        "workspace_revisions",
        "mode_executions",
        "objects",
        "object_links",
    )
    messaging_tables = ("workspace_outbox", "workspace_inbox_receipts", "workspace_idempotency")
    for table in organization_tables:
        _enable_rls("organization", table, workspace=False)
    for table in workspace_tables:
        _enable_rls("workspace", table, workspace=True)
    _enable_rls("audit", "workspace_records", workspace=True)
    for table in messaging_tables:
        _enable_rls("messaging", table, workspace=True)


def _enable_rls(schema: str, table: str, *, workspace: bool) -> None:
    qualified = f'"{schema}"."{table}"'
    predicate = "organization_id = NULLIF(current_setting('asd.organization_id', true), '')::uuid"
    if workspace:
        predicate += (
            " AND workspace_id = NULLIF(current_setting('asd.workspace_id', true), '')::uuid"
        )
    op.execute(f"ALTER TABLE {qualified} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {qualified} FORCE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY {table}_scope_policy ON {qualified} FOR ALL TO asd_app USING ({predicate}) WITH CHECK ({predicate})"
    )


def downgrade() -> None:
    if os.environ.get("ASD_ALLOW_DESTRUCTIVE_DOWNGRADE") != "1":
        raise RuntimeError(
            "destructive downgrade is forbidden; set ASD_ALLOW_DESTRUCTIVE_DOWNGRADE=1 "
            "only for a disposable development/test database"
        )
    for schema in reversed(SCHEMAS):
        op.execute(sa.schema.DropSchema(schema, cascade=True, if_exists=True))
    # Cluster-scoped NOLOGIN role is intentionally retained. Production rollback
    # is forward repair or verified restore, never this downgrade.
