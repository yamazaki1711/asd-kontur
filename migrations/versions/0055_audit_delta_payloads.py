"""Persist causal paths and package memberships behind immutable Audit deltas.

Revision ID: 0055_audit_delta_payloads
Revises: 0054_align_audit_process_state
"""

from __future__ import annotations

import os

from alembic import op

revision = "0055_audit_delta_payloads"
down_revision = "0054_align_audit_process_state"
branch_labels = None
depends_on = None

_TABLES = ("audit_causal_path_versions", "audit_package_delta_memberships")


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE workspace.audit_causal_path_versions (
          organization_id uuid NOT NULL, workspace_id uuid NOT NULL,
          causal_delta_id uuid NOT NULL, delta_version bigint NOT NULL,
          path_id uuid NOT NULL, material_batch_ref text NOT NULL,
          incoming_control_ref text, admission_ref text, work_ref text,
          evidence_ref text, id_package_ref text, presented_volume_ref text,
          ks_ref text, payment_claim_ref text,
          state text NOT NULL CHECK (state IN ('satisfied','missing','conflict','indeterminate','not_applicable','blocked')),
          rule_trace_ids uuid[] NOT NULL, gap_codes text[] NOT NULL,
          downstream_impacts text[] NOT NULL,
          fingerprint text NOT NULL CHECK (fingerprint ~ '^sha256:[a-f0-9]{64}$'),
          PRIMARY KEY (organization_id,workspace_id,causal_delta_id,delta_version,path_id),
          FOREIGN KEY (organization_id,workspace_id,causal_delta_id,delta_version)
            REFERENCES workspace.audit_delta_versions(organization_id,workspace_id,audit_delta_id,version)
            ON DELETE RESTRICT
        );
        CREATE TABLE workspace.audit_package_delta_memberships (
          organization_id uuid NOT NULL, workspace_id uuid NOT NULL,
          package_readiness_id uuid NOT NULL, delta_version bigint NOT NULL,
          package_id uuid NOT NULL, package_version bigint NOT NULL,
          PRIMARY KEY (organization_id,workspace_id,package_readiness_id,delta_version,package_id,package_version),
          FOREIGN KEY (organization_id,workspace_id,package_readiness_id,delta_version)
            REFERENCES workspace.audit_delta_versions(organization_id,workspace_id,audit_delta_id,version)
            ON DELETE RESTRICT,
          FOREIGN KEY (organization_id,workspace_id,package_id,package_version)
            REFERENCES workspace.audit_package_versions(organization_id,workspace_id,package_id,version)
            ON DELETE RESTRICT
        );
        """
    )
    predicate = (
        "organization_id = nullif(current_setting('asd.organization_id',true),'')::uuid "
        "AND workspace_id = nullif(current_setting('asd.workspace_id',true),'')::uuid"
    )
    for table in _TABLES:
        op.execute(f"ALTER TABLE workspace.{table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE workspace.{table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY {table}_audit_scope_policy ON workspace.{table} "
            f"FOR ALL TO asd_audit_service USING ({predicate}) WITH CHECK ({predicate})"
        )
        op.execute(
            f"CREATE POLICY {table}_destruction_scope_policy ON workspace.{table} "
            f"FOR ALL TO asd_destruction_executor USING ({predicate}) WITH CHECK ({predicate})"
        )
        op.execute(f"GRANT SELECT,INSERT ON workspace.{table} TO asd_audit_service")
        op.execute(f"GRANT SELECT,DELETE ON workspace.{table} TO asd_destruction_executor")
        op.execute(
            f"CREATE TRIGGER {table}_immutable_guard BEFORE UPDATE OR DELETE ON workspace.{table} "
            "FOR EACH ROW EXECUTE FUNCTION workspace.reject_audit_version_mutation()"
        )


def downgrade() -> None:
    if os.environ.get("ASD_ALLOW_DESTRUCTIVE_DOWNGRADE") != "1":
        raise RuntimeError("Audit delta payload downgrade requires a disposable database")
    for table in reversed(_TABLES):
        op.execute(f"DROP TABLE workspace.{table}")
