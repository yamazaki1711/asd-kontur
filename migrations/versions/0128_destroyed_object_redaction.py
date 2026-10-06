"""Redact names of destroyed workspace-owned construction objects safely.

Revision ID: 0128_destroyed_object_redaction
Revises: 0127_task_scoped_quantity_profile
"""

from alembic import op

revision = "0128_destroyed_object_redaction"
down_revision = "0127_task_scoped_quantity_profile"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE FUNCTION application.redact_destroyed_construction_object(
            p_organization uuid, p_workspace uuid, p_object uuid
        ) RETURNS boolean
        LANGUAGE plpgsql SECURITY DEFINER
        SET search_path = pg_catalog
        AS $$
        DECLARE changed integer;
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM workspace.workspaces w
                WHERE w.organization_id=p_organization
                  AND w.workspace_id=p_workspace
                  AND w.construction_object_id=p_object
                  AND w.lifecycle_state='DESTROYED'
            ) THEN
                RAISE EXCEPTION 'construction_object_redaction_requires_destroyed';
            END IF;
            IF EXISTS (
                SELECT 1 FROM workspace.workspaces w
                WHERE w.organization_id=p_organization
                  AND w.construction_object_id=p_object
                  AND w.lifecycle_state<>'DESTROYED'
            ) THEN
                RETURN false;
            END IF;
            UPDATE organization.construction_objects c
               SET display_name='Удалённый объект', external_id=NULL,
                   status='closed', revision=c.revision+1
             WHERE c.organization_id=p_organization
               AND c.construction_object_id=p_object
               AND (c.display_name<>'Удалённый объект'
                    OR c.external_id IS NOT NULL OR c.status<>'closed');
            GET DIAGNOSTICS changed = ROW_COUNT;
            RETURN changed > 0;
        END;
        $$;
        """
    )
    op.execute(
        "REVOKE ALL ON FUNCTION application.redact_destroyed_construction_object"
        "(uuid,uuid,uuid) FROM PUBLIC"
    )
    op.execute(
        "GRANT EXECUTE ON FUNCTION application.redact_destroyed_construction_object"
        "(uuid,uuid,uuid) TO asd_app"
    )


def downgrade() -> None:
    op.execute(
        "DROP FUNCTION application.redact_destroyed_construction_object(uuid,uuid,uuid)"
    )
