"""Store explicit, versioned contractor inputs for Tender decisions.

Revision ID: 0132_tender_participation_assessments
Revises: 0131_contract_revision_review
"""

from __future__ import annotations

import os

from alembic import op

revision = "0132_tender_participation_assessments"
down_revision = "0131_contract_revision_review"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE workspace.tender_participation_assessments (
          organization_id uuid NOT NULL,
          workspace_id uuid NOT NULL,
          assessment_id uuid NOT NULL,
          assessment jsonb NOT NULL,
          assessment_digest text NOT NULL CHECK (assessment_digest ~ '^sha256:[a-f0-9]{64}$'),
          submitted_by text NOT NULL,
          submitted_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
          PRIMARY KEY (organization_id,workspace_id,assessment_id),
          FOREIGN KEY (organization_id,workspace_id)
            REFERENCES workspace.workspaces(organization_id,workspace_id) ON DELETE RESTRICT
        )
        """
    )
    op.execute(
        "CREATE INDEX tender_participation_assessments_latest_idx ON "
        "workspace.tender_participation_assessments "
        "(organization_id,workspace_id,submitted_at DESC,assessment_id DESC)"
    )
    op.execute("ALTER TABLE workspace.tender_participation_assessments ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE workspace.tender_participation_assessments FORCE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY tender_participation_assessments_scope ON "
        "workspace.tender_participation_assessments USING "
        "(organization_id=NULLIF(current_setting('asd.organization_id',true),'')::uuid "
        "AND workspace_id=NULLIF(current_setting('asd.workspace_id',true),'')::uuid) "
        "WITH CHECK (organization_id=NULLIF(current_setting('asd.organization_id',true),'')::uuid "
        "AND workspace_id=NULLIF(current_setting('asd.workspace_id',true),'')::uuid)"
    )
    op.execute("GRANT SELECT,INSERT ON workspace.tender_participation_assessments TO asd_app")
    op.execute(
        "GRANT SELECT,DELETE ON workspace.tender_participation_assessments "
        "TO asd_destruction_executor"
    )
    op.execute(
        "CREATE TRIGGER tender_participation_assessments_immutable BEFORE UPDATE OR DELETE "
        "ON workspace.tender_participation_assessments FOR EACH ROW EXECUTE FUNCTION "
        "application.reject_spine_mutation_except_destruction()"
    )
    op.execute(
        """
        CREATE FUNCTION workspace.reject_fenced_tender_participation_assessment()
        RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER
        SET search_path = pg_catalog, workspace AS $$
        DECLARE current_state text;
        DECLARE fenced boolean;
        BEGIN
          SELECT lifecycle_state,write_fenced INTO current_state,fenced
          FROM workspace.workspaces
          WHERE organization_id=NEW.organization_id AND workspace_id=NEW.workspace_id
          FOR SHARE;
          IF current_state IS DISTINCT FROM 'ACTIVE' OR fenced IS DISTINCT FROM false THEN
            RAISE EXCEPTION 'tender_workspace_not_active';
          END IF;
          RETURN NEW;
        END $$
        """
    )
    op.execute(
        "CREATE TRIGGER tender_participation_assessments_active BEFORE INSERT "
        "ON workspace.tender_participation_assessments FOR EACH ROW EXECUTE FUNCTION "
        "workspace.reject_fenced_tender_participation_assessment()"
    )


def downgrade() -> None:
    if os.environ.get("ASD_ALLOW_DESTRUCTIVE_DOWNGRADE") != "1":
        raise RuntimeError("Tender participation downgrade requires a disposable database")
    op.execute("DROP TABLE workspace.tender_participation_assessments")
    op.execute("DROP FUNCTION workspace.reject_fenced_tender_participation_assessment()")
