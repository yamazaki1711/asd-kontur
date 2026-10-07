"""Persist workspace-scoped incoming-inspection preflights, not admission decisions.

Revision ID: 0135_support_incoming_inspection_preflights
Revises: 0134_contract_coherence_profile_v2
"""

from __future__ import annotations

import os

from alembic import op

revision = "0135_support_incoming_inspection_preflights"
down_revision = "0134_contract_coherence_profile_v2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE workspace.support_incoming_inspection_preflights (
          organization_id uuid NOT NULL,
          workspace_id uuid NOT NULL,
          preflight_id uuid NOT NULL,
          idempotency_key text NOT NULL,
          material_name text NOT NULL,
          batch_reference text NOT NULL,
          inspection jsonb NOT NULL,
          result jsonb NOT NULL,
          payload_digest text NOT NULL CHECK (payload_digest ~ '^sha256:[a-f0-9]{64}$'),
          submitted_by text NOT NULL,
          submitted_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
          PRIMARY KEY (organization_id,workspace_id,preflight_id),
          UNIQUE (organization_id,workspace_id,idempotency_key),
          FOREIGN KEY (organization_id,workspace_id)
            REFERENCES workspace.workspaces(organization_id,workspace_id) ON DELETE RESTRICT
        )
        """
    )
    op.execute(
        "CREATE INDEX support_incoming_inspection_latest_idx ON "
        "workspace.support_incoming_inspection_preflights "
        "(organization_id,workspace_id,submitted_at DESC,preflight_id DESC)"
    )
    op.execute("ALTER TABLE workspace.support_incoming_inspection_preflights ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE workspace.support_incoming_inspection_preflights FORCE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY support_incoming_inspection_scope ON "
        "workspace.support_incoming_inspection_preflights USING "
        "(organization_id=NULLIF(current_setting('asd.organization_id',true),'')::uuid "
        "AND workspace_id=NULLIF(current_setting('asd.workspace_id',true),'')::uuid) "
        "WITH CHECK (organization_id=NULLIF(current_setting('asd.organization_id',true),'')::uuid "
        "AND workspace_id=NULLIF(current_setting('asd.workspace_id',true),'')::uuid)"
    )
    op.execute("GRANT SELECT,INSERT ON workspace.support_incoming_inspection_preflights TO asd_app")
    op.execute(
        "GRANT SELECT,DELETE ON workspace.support_incoming_inspection_preflights "
        "TO asd_destruction_executor"
    )
    op.execute(
        "CREATE TRIGGER support_incoming_inspection_immutable BEFORE UPDATE OR DELETE "
        "ON workspace.support_incoming_inspection_preflights FOR EACH ROW EXECUTE FUNCTION "
        "application.reject_spine_mutation_except_destruction()"
    )
    op.execute(
        """
        CREATE FUNCTION workspace.reject_fenced_support_incoming_inspection()
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
            RAISE EXCEPTION 'support_workspace_not_active';
          END IF;
          RETURN NEW;
        END $$
        """
    )
    op.execute(
        "CREATE TRIGGER support_incoming_inspection_active BEFORE INSERT "
        "ON workspace.support_incoming_inspection_preflights FOR EACH ROW EXECUTE FUNCTION "
        "workspace.reject_fenced_support_incoming_inspection()"
    )


def downgrade() -> None:
    if os.environ.get("ASD_ALLOW_DESTRUCTIVE_DOWNGRADE") != "1":
        raise RuntimeError("Incoming-inspection downgrade requires a disposable database")
    op.execute("DROP TABLE workspace.support_incoming_inspection_preflights")
    op.execute("DROP FUNCTION workspace.reject_fenced_support_incoming_inspection()")
