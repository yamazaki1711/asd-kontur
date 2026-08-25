"""Use methodological_practice for new canonical source guidance.

Revision ID: 0015_practice_authority
Revises: 0014_playbook_roles

Migration 0009 and its already-published rows remain immutable evidence.  The
legacy authority value stays readable, while every new publication uses the
owner-accepted methodological_practice layer.
"""

from __future__ import annotations

import os

from alembic import op

revision = "0015_practice_authority"
down_revision = "0014_playbook_roles"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        DO $$ DECLARE constraint_name name; BEGIN
          SELECT conname INTO constraint_name FROM pg_constraint
          WHERE conrelid='platform.practice_guidance_units'::regclass
            AND contype='c' AND pg_get_constraintdef(oid) LIKE '%authority_layer%';
          IF constraint_name IS NOT NULL THEN
            EXECUTE format(
              'ALTER TABLE platform.practice_guidance_units DROP CONSTRAINT %I',
              constraint_name
            );
          END IF;
        END $$;
        ALTER TABLE platform.practice_guidance_units
          ADD CONSTRAINT practice_guidance_units_authority_ck
          CHECK (authority_layer IN (
            'methodological_guidance','methodological_practice'
          ));
        """
    )


def downgrade() -> None:
    if os.environ.get("ASD_ALLOW_DESTRUCTIVE_DOWNGRADE") != "1":
        raise RuntimeError("Practice authority downgrade requires a disposable database")
    op.execute(
        """
        DO $$ BEGIN
          IF EXISTS (
            SELECT 1 FROM platform.practice_guidance_units
            WHERE authority_layer='methodological_practice'
          ) THEN
            RAISE EXCEPTION
              'Cannot downgrade while methodological_practice guidance rows exist';
          END IF;
        END $$;
        ALTER TABLE platform.practice_guidance_units
          DROP CONSTRAINT practice_guidance_units_authority_ck;
        ALTER TABLE platform.practice_guidance_units
          ADD CONSTRAINT practice_guidance_units_authority_layer_check
          CHECK (authority_layer='methodological_guidance');
        """
    )
