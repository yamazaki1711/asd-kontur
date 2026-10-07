"""Permit qualified Support confirmation of field-document material-use evidence.

Revision ID: 0138_support_material_use_evidence
Revises: 0137_support_material_application_basis
"""

from __future__ import annotations

import os

from alembic import op

revision = "0138_support_material_use_evidence"
down_revision = "0137_support_material_application_basis"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE workspace.support_material_use_confirmations (
          organization_id uuid NOT NULL,
          workspace_id uuid NOT NULL,
          confirmation_id uuid NOT NULL,
          idempotency_key text NOT NULL CHECK (length(btrim(idempotency_key)) BETWEEN 8 AND 200),
          admission_id uuid NOT NULL,
          work_instance_id uuid NOT NULL,
          work_instance_version bigint NOT NULL,
          source_version_id uuid NOT NULL,
          source_locator_id uuid NOT NULL,
          evidence_link_id uuid NOT NULL,
          professional_grant_id uuid NOT NULL,
          professional_grant_version bigint NOT NULL,
          submitted_by text NOT NULL,
          confirmation_statement text NOT NULL
            CHECK (length(btrim(confirmation_statement)) BETWEEN 3 AND 1000),
          confirmation_fingerprint text NOT NULL
            CHECK (confirmation_fingerprint ~ '^sha256:[a-f0-9]{64}$'),
          recorded_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
          PRIMARY KEY (organization_id,workspace_id,confirmation_id),
          UNIQUE (organization_id,workspace_id,idempotency_key),
          UNIQUE (organization_id,workspace_id,evidence_link_id),
          FOREIGN KEY (organization_id,workspace_id,admission_id)
            REFERENCES workspace.support_material_admissions
            (organization_id,workspace_id,admission_id) ON DELETE RESTRICT,
          FOREIGN KEY (organization_id,workspace_id,work_instance_id,work_instance_version)
            REFERENCES workspace.work_instance_versions
            (organization_id,workspace_id,work_instance_id,version) ON DELETE RESTRICT,
          FOREIGN KEY (organization_id,workspace_id,source_version_id)
            REFERENCES workspace.source_versions
            (organization_id,workspace_id,source_version_id) ON DELETE RESTRICT,
          FOREIGN KEY (organization_id,workspace_id,source_locator_id)
            REFERENCES workspace.source_locators
            (organization_id,workspace_id,source_locator_id) ON DELETE RESTRICT,
          FOREIGN KEY (organization_id,workspace_id,evidence_link_id)
            REFERENCES workspace.evidence_links
            (organization_id,workspace_id,evidence_link_id) ON DELETE RESTRICT,
          FOREIGN KEY (organization_id,workspace_id,professional_grant_id,
                       professional_grant_version)
            REFERENCES workspace.support_professional_grants
            (organization_id,workspace_id,grant_id,grant_version) ON DELETE RESTRICT
        )
        """
    )
    op.execute("ALTER TABLE workspace.support_material_use_confirmations ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE workspace.support_material_use_confirmations FORCE ROW LEVEL SECURITY")
    predicate = (
        "organization_id=NULLIF(current_setting('asd.organization_id',true),'')::uuid "
        "AND workspace_id=NULLIF(current_setting('asd.workspace_id',true),'')::uuid"
    )
    for role, command in (
        ("asd_app", "SELECT"),
        ("asd_support_service", "SELECT,INSERT"),
        ("asd_destruction_executor", "SELECT,DELETE"),
    ):
        op.execute(f"GRANT {command} ON workspace.support_material_use_confirmations TO {role}")
        op.execute(
            f"CREATE POLICY support_material_use_confirmations_{role} ON "
            "workspace.support_material_use_confirmations "
            f"FOR ALL TO {role} USING ({predicate}) WITH CHECK ({predicate})"
        )
    op.execute(
        "CREATE TRIGGER support_material_use_immutable BEFORE UPDATE OR DELETE ON "
        "workspace.support_material_use_confirmations FOR EACH ROW EXECUTE FUNCTION "
        "application.reject_spine_mutation_except_destruction()"
    )
    op.execute(
        "CREATE TRIGGER support_material_use_active BEFORE INSERT ON "
        "workspace.support_material_use_confirmations FOR EACH ROW EXECUTE FUNCTION "
        "workspace.reject_fenced_support_incoming_inspection()"
    )
    op.execute("GRANT INSERT ON workspace.evidence_links TO asd_support_service")
    op.execute(
        "CREATE POLICY evidence_links_support_material_use_insert ON "
        "workspace.evidence_links FOR INSERT TO asd_support_service WITH CHECK "
        "(organization_id=NULLIF(current_setting('asd.organization_id',true),'')::uuid "
        "AND workspace_id=NULLIF(current_setting('asd.workspace_id',true),'')::uuid "
        "AND subject_type='work_instance' AND evidence_role='material_application' "
        "AND validity_status='verified')"
    )


def downgrade() -> None:
    if os.environ.get("ASD_ALLOW_DESTRUCTIVE_DOWNGRADE") != "1":
        raise RuntimeError("Material-use evidence downgrade requires a disposable database")
    op.execute("DROP POLICY evidence_links_support_material_use_insert ON workspace.evidence_links")
    op.execute("REVOKE INSERT ON workspace.evidence_links FROM asd_support_service")
    op.execute("DROP TABLE workspace.support_material_use_confirmations")
