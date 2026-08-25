"""Add missing typed PracticePlaybook member roles.

Revision ID: 0014_playbook_roles
Revises: 0013_guide_editions
"""

from __future__ import annotations

import os

from alembic import op

revision = "0014_playbook_roles"
down_revision = "0013_guide_editions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE platform.practice_playbook_members
          DROP CONSTRAINT practice_playbook_members_member_role_check;
        ALTER TABLE platform.practice_playbook_members
          ADD CONSTRAINT practice_playbook_members_member_role_check CHECK (
            member_role IN (
              'principle','workflow_step','form_guidance','field_guidance',
              'completion_instruction','attention_point','allowed_variant','rationale',
              'failure_pattern','checklist','completeness','journal_selection',
              'dependency','signer_guidance','visual_example'
            )
          );
        """
    )


def downgrade() -> None:
    if os.environ.get("ASD_ALLOW_DESTRUCTIVE_DOWNGRADE") != "1":
        raise RuntimeError("PracticePlaybook role downgrade requires a disposable database")
    op.execute(
        """
        DELETE FROM platform.practice_playbook_members
          WHERE member_role IN ('completion_instruction','signer_guidance');
        ALTER TABLE platform.practice_playbook_members
          DROP CONSTRAINT practice_playbook_members_member_role_check;
        ALTER TABLE platform.practice_playbook_members
          ADD CONSTRAINT practice_playbook_members_member_role_check CHECK (
            member_role IN (
              'principle','workflow_step','form_guidance','field_guidance',
              'attention_point','allowed_variant','rationale','failure_pattern',
              'checklist','completeness','journal_selection','dependency','visual_example'
            )
          );
        """
    )
