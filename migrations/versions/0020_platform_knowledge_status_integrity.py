"""Expose canonical practice conflict and quarantine counts to the application.

Revision ID: 0020_knowledge_status
Revises: 0019_memory_integrity
"""

from __future__ import annotations

from alembic import op

revision = "0020_knowledge_status"
down_revision = "0019_memory_integrity"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE FUNCTION application.get_platform_practice_conflict_status()
        RETURNS jsonb
        LANGUAGE sql STABLE SECURITY DEFINER
        SET search_path = pg_catalog, application, platform
        AS $$
          SELECT jsonb_build_object(
            'conflict_count',count(DISTINCT guidance_conflict_id),
            'quarantine_count',count(DISTINCT (guidance_candidate_id,candidate_version))
              FILTER (WHERE guidance_unit_id IS NULL)
          )
          FROM platform.practice_guidance_conflicts
          WHERE state='open'
        $$;
        REVOKE ALL ON FUNCTION application.get_platform_practice_conflict_status()
          FROM PUBLIC;
        GRANT EXECUTE ON FUNCTION application.get_platform_practice_conflict_status()
          TO asd_app;
        """
    )


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS application.get_platform_practice_conflict_status()")
