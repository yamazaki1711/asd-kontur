"""Bind actual Support material application to admission, evidence and authority.

Revision ID: 0137_support_material_application_basis
Revises: 0136_support_material_admission_basis
"""

from __future__ import annotations

import os

from alembic import op

revision = "0137_support_material_application_basis"
down_revision = "0136_support_material_admission_basis"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE workspace.material_applications "
        "ADD COLUMN admission_id uuid, "
        "ADD COLUMN authority_grant_id uuid, "
        "ADD COLUMN authority_grant_version bigint, "
        "ADD COLUMN idempotency_key text, "
        "ADD COLUMN decision_basis text"
    )
    op.execute(
        "ALTER TABLE workspace.material_applications ADD CONSTRAINT "
        "material_applications_admission_fk FOREIGN KEY "
        "(organization_id,workspace_id,admission_id) REFERENCES "
        "workspace.support_material_admissions"
        "(organization_id,workspace_id,admission_id) ON DELETE RESTRICT NOT VALID"
    )
    op.execute(
        "ALTER TABLE workspace.material_applications ADD CONSTRAINT "
        "material_applications_grant_fk FOREIGN KEY "
        "(organization_id,workspace_id,authority_grant_id,authority_grant_version) "
        "REFERENCES workspace.support_professional_grants"
        "(organization_id,workspace_id,grant_id,grant_version) ON DELETE RESTRICT NOT VALID"
    )
    op.execute(
        "ALTER TABLE workspace.material_applications ADD CONSTRAINT "
        "material_applications_qualified_basis CHECK "
        "(admission_id IS NOT NULL AND authority_grant_id IS NOT NULL AND "
        "authority_grant_version IS NOT NULL AND idempotency_key IS NOT NULL AND "
        "decision_basis IS NOT NULL AND "
        "length(btrim(idempotency_key)) BETWEEN 8 AND 200 AND "
        "length(btrim(decision_basis)) BETWEEN 3 AND 1000 AND "
        "quantity > 0 AND precision_scale BETWEEN 0 AND 6) NOT VALID"
    )
    op.execute(
        "CREATE UNIQUE INDEX material_applications_idempotency_idx ON "
        "workspace.material_applications(organization_id,workspace_id,idempotency_key) "
        "WHERE idempotency_key IS NOT NULL"
    )
    op.execute("GRANT SELECT ON workspace.material_applications TO asd_app")
    op.execute("GRANT INSERT ON workspace.material_applications TO asd_support_service")
    op.execute("GRANT SELECT ON workspace.source_artifacts TO asd_support_service")
    op.execute(
        "CREATE POLICY source_artifacts_support_read ON workspace.source_artifacts "
        "FOR SELECT TO asd_support_service USING "
        "(organization_id=NULLIF(current_setting('asd.organization_id',true),'')::uuid "
        "AND workspace_id=NULLIF(current_setting('asd.workspace_id',true),'')::uuid)"
    )
    op.execute(
        "CREATE POLICY material_applications_app_read ON "
        "workspace.material_applications FOR SELECT TO asd_app USING "
        "(organization_id=NULLIF(current_setting('asd.organization_id',true),'')::uuid "
        "AND workspace_id=NULLIF(current_setting('asd.workspace_id',true),'')::uuid)"
    )
    op.execute(
        "CREATE POLICY material_applications_support_insert ON "
        "workspace.material_applications FOR INSERT TO asd_support_service WITH CHECK "
        "(organization_id=NULLIF(current_setting('asd.organization_id',true),'')::uuid "
        "AND workspace_id=NULLIF(current_setting('asd.workspace_id',true),'')::uuid)"
    )
    op.execute(
        "CREATE TRIGGER material_applications_active BEFORE INSERT ON "
        "workspace.material_applications FOR EACH ROW EXECUTE FUNCTION "
        "workspace.reject_fenced_support_incoming_inspection()"
    )


def downgrade() -> None:
    if os.environ.get("ASD_ALLOW_DESTRUCTIVE_DOWNGRADE") != "1":
        raise RuntimeError("Material-application downgrade requires a disposable database")
    op.execute("DROP TRIGGER material_applications_active ON workspace.material_applications")
    op.execute(
        "DROP POLICY material_applications_support_insert ON workspace.material_applications"
    )
    op.execute("DROP POLICY material_applications_app_read ON workspace.material_applications")
    op.execute("DROP POLICY source_artifacts_support_read ON workspace.source_artifacts")
    op.execute("REVOKE SELECT ON workspace.source_artifacts FROM asd_support_service")
    op.execute("REVOKE INSERT ON workspace.material_applications FROM asd_support_service")
    op.execute("REVOKE SELECT ON workspace.material_applications FROM asd_app")
    op.execute("DROP INDEX workspace.material_applications_idempotency_idx")
    op.execute(
        "ALTER TABLE workspace.material_applications DROP CONSTRAINT "
        "material_applications_qualified_basis"
    )
    op.execute(
        "ALTER TABLE workspace.material_applications DROP CONSTRAINT material_applications_grant_fk"
    )
    op.execute(
        "ALTER TABLE workspace.material_applications DROP CONSTRAINT "
        "material_applications_admission_fk"
    )
    op.execute(
        "ALTER TABLE workspace.material_applications DROP COLUMN admission_id, "
        "DROP COLUMN authority_grant_id, DROP COLUMN authority_grant_version, "
        "DROP COLUMN idempotency_key, DROP COLUMN decision_basis"
    )
