"""Record the factual basis of a Support material-admission decision.

Revision ID: 0136_support_material_admission_basis
Revises: 0135_support_incoming_inspection_preflights
"""

from __future__ import annotations

import os

from alembic import op

revision = "0136_support_material_admission_basis"
down_revision = "0135_support_incoming_inspection_preflights"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("GRANT SELECT ON platform.material_class_versions TO asd_app")
    op.execute("GRANT SELECT ON platform.work_type_versions TO asd_app")
    op.execute("GRANT SELECT ON workspace.support_material_admissions TO asd_app")
    op.execute(
        "GRANT SELECT ON workspace.support_incoming_inspection_preflights "
        "TO asd_support_service"
    )
    op.execute(
        "CREATE POLICY support_incoming_inspection_support_read ON "
        "workspace.support_incoming_inspection_preflights FOR SELECT TO asd_support_service "
        "USING (organization_id=NULLIF(current_setting('asd.organization_id',true),'')::uuid "
        "AND workspace_id=NULLIF(current_setting('asd.workspace_id',true),'')::uuid)"
    )
    op.execute(
        "CREATE POLICY support_material_admissions_app_read ON "
        "workspace.support_material_admissions FOR SELECT TO asd_app USING "
        "(organization_id=NULLIF(current_setting('asd.organization_id',true),'')::uuid "
        "AND workspace_id=NULLIF(current_setting('asd.workspace_id',true),'')::uuid)"
    )
    op.execute(
        "ALTER TABLE workspace.support_incoming_inspection_preflights "
        "ADD COLUMN material_batch_id uuid,ADD COLUMN material_batch_version bigint"
    )
    op.execute(
        "ALTER TABLE workspace.support_incoming_inspection_preflights ADD CONSTRAINT "
        "support_incoming_inspection_batch_pair CHECK "
        "((material_batch_id IS NULL) = (material_batch_version IS NULL)) NOT VALID"
    )
    op.execute(
        "ALTER TABLE workspace.support_incoming_inspection_preflights ADD CONSTRAINT "
        "support_incoming_inspection_batch_fk FOREIGN KEY "
        "(organization_id,workspace_id,material_batch_id,material_batch_version) "
        "REFERENCES workspace.material_batch_versions"
        "(organization_id,workspace_id,material_batch_id,version) ON DELETE RESTRICT NOT VALID"
    )
    op.execute(
        "CREATE INDEX support_incoming_inspection_batch_latest_idx ON "
        "workspace.support_incoming_inspection_preflights "
        "(organization_id,workspace_id,material_batch_id,material_batch_version,"
        "submitted_at DESC,preflight_id DESC) WHERE material_batch_id IS NOT NULL"
    )
    op.execute(
        """
        ALTER TABLE workspace.support_material_admissions
          ADD COLUMN manufacturer_ref text,
          ADD COLUMN supplier_ref text,
          ADD COLUMN applicable_to_work boolean,
          ADD COLUMN delivered_quantity numeric(24,6),
          ADD COLUMN delivered_unit text,
          ADD COLUMN quantity_evidence_link_id uuid,
          ADD COLUMN decision_basis text,
          ADD COLUMN idempotency_key text
        """
    )
    op.execute(
        "CREATE UNIQUE INDEX support_material_admissions_idempotency_idx ON "
        "workspace.support_material_admissions "
        "(organization_id,workspace_id,idempotency_key) "
        "WHERE idempotency_key IS NOT NULL"
    )
    op.execute(
        "ALTER TABLE workspace.support_material_admissions ADD CONSTRAINT "
        "support_material_admissions_incoming_preflight_fk FOREIGN KEY "
        "(organization_id,workspace_id,incoming_control_id) REFERENCES "
        "workspace.support_incoming_inspection_preflights"
        "(organization_id,workspace_id,preflight_id) ON DELETE RESTRICT NOT VALID"
    )
    op.execute(
        "ALTER TABLE workspace.support_material_admissions ADD CONSTRAINT "
        "support_material_admissions_quantity_evidence_fk FOREIGN KEY "
        "(organization_id,workspace_id,quantity_evidence_link_id) REFERENCES "
        "workspace.evidence_links(organization_id,workspace_id,evidence_link_id) "
        "ON DELETE RESTRICT NOT VALID"
    )
    op.execute(
        "ALTER TABLE workspace.support_material_admissions ADD CONSTRAINT "
        "support_material_admissions_positive_quantity CHECK "
        "(delivered_quantity IS NULL OR delivered_quantity > 0) NOT VALID"
    )
    op.execute(
        "ALTER TABLE workspace.support_material_admissions ADD CONSTRAINT "
        "support_material_admissions_new_basis CHECK "
        "(idempotency_key IS NULL OR "
        "(coalesce(length(btrim(manufacturer_ref)),0) >= 2 AND "
        "coalesce(length(btrim(supplier_ref)),0) >= 2 AND "
        "applicable_to_work IS NOT NULL AND "
        "delivered_quantity > 0 AND "
        "coalesce(length(btrim(delivered_unit)),0) >= 1 AND "
        "quantity_evidence_link_id IS NOT NULL AND "
        "coalesce(length(btrim(decision_basis)),0) >= 3 AND "
        "incoming_control_id IS NOT NULL)) NOT VALID"
    )


def downgrade() -> None:
    if os.environ.get("ASD_ALLOW_DESTRUCTIVE_DOWNGRADE") != "1":
        raise RuntimeError("Material-admission downgrade requires a disposable database")
    op.execute("REVOKE SELECT ON platform.material_class_versions FROM asd_app")
    op.execute("REVOKE SELECT ON platform.work_type_versions FROM asd_app")
    op.execute("REVOKE SELECT ON workspace.support_material_admissions FROM asd_app")
    op.execute(
        "DROP POLICY support_incoming_inspection_support_read ON "
        "workspace.support_incoming_inspection_preflights"
    )
    op.execute(
        "REVOKE SELECT ON workspace.support_incoming_inspection_preflights "
        "FROM asd_support_service"
    )
    op.execute(
        "DROP POLICY support_material_admissions_app_read ON "
        "workspace.support_material_admissions"
    )
    op.execute(
        "ALTER TABLE workspace.support_material_admissions DROP CONSTRAINT "
        "support_material_admissions_new_basis"
    )
    op.execute(
        "ALTER TABLE workspace.support_material_admissions DROP CONSTRAINT "
        "support_material_admissions_positive_quantity"
    )
    op.execute(
        "ALTER TABLE workspace.support_material_admissions DROP CONSTRAINT "
        "support_material_admissions_quantity_evidence_fk"
    )
    op.execute(
        "ALTER TABLE workspace.support_material_admissions DROP CONSTRAINT "
        "support_material_admissions_incoming_preflight_fk"
    )
    op.execute("DROP INDEX workspace.support_material_admissions_idempotency_idx")
    op.execute(
        "ALTER TABLE workspace.support_material_admissions "
        "DROP COLUMN manufacturer_ref,DROP COLUMN supplier_ref,"
        "DROP COLUMN applicable_to_work,DROP COLUMN delivered_quantity,"
        "DROP COLUMN delivered_unit,DROP COLUMN quantity_evidence_link_id,"
        "DROP COLUMN decision_basis,DROP COLUMN idempotency_key"
    )
    op.execute(
        "ALTER TABLE workspace.support_incoming_inspection_preflights "
        "DROP CONSTRAINT support_incoming_inspection_batch_fk"
    )
    op.execute("DROP INDEX workspace.support_incoming_inspection_batch_latest_idx")
    op.execute(
        "ALTER TABLE workspace.support_incoming_inspection_preflights "
        "DROP CONSTRAINT support_incoming_inspection_batch_pair"
    )
    op.execute(
        "ALTER TABLE workspace.support_incoming_inspection_preflights "
        "DROP COLUMN material_batch_id,DROP COLUMN material_batch_version"
    )
