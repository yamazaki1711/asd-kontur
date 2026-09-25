"""Scope engineering candidates to the semantic profile that produced them.

Revision ID: 0047_profile_scoped_engineering_candidates
Revises: 0046_structure_relationship_candidates
"""

from __future__ import annotations

import os

from alembic import op

revision = "0047_profile_scoped_engineering_candidates"
down_revision = "0046_structure_relationship_candidates"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Keep existing observations immutable while making future selection explicit."""
    op.execute(
        "ALTER TABLE workspace.project_structure_node_versions "
        "ADD COLUMN extraction_profile_version text NOT NULL "
        "DEFAULT 'project-definition-extraction-v0.1' "
        "CHECK (lower(extraction_profile_version) <> 'latest')"
    )
    op.execute(
        "ALTER TABLE workspace.project_structure_relationship_candidates "
        "ADD COLUMN extraction_profile_version text NOT NULL "
        "DEFAULT 'project-definition-extraction-v0.1' "
        "CHECK (lower(extraction_profile_version) <> 'latest')"
    )
    op.execute(
        "ALTER TABLE workspace.project_reconciliation_defects "
        "ADD COLUMN extraction_profile_version text NOT NULL "
        "DEFAULT 'project-definition-extraction-v0.1' "
        "CHECK (lower(extraction_profile_version) <> 'latest')"
    )
    op.execute(
        "CREATE INDEX project_structure_node_versions_profile_locator_idx ON "
        "workspace.project_structure_node_versions "
        "(organization_id, workspace_id, extraction_profile_version, source_locator_id)"
    )
    op.execute(
        "CREATE INDEX project_structure_relationship_candidates_profile_source_idx ON "
        "workspace.project_structure_relationship_candidates "
        "(organization_id, workspace_id, source_version_id, extraction_profile_version)"
    )
    op.execute(
        "CREATE INDEX project_reconciliation_defects_profile_idx ON "
        "workspace.project_reconciliation_defects "
        "(organization_id, workspace_id, extraction_profile_version, status)"
    )


def downgrade() -> None:
    if os.environ.get("ASD_ALLOW_DESTRUCTIVE_DOWNGRADE") != "1":
        raise RuntimeError("Profile provenance downgrade requires a disposable database")
    op.execute("DROP INDEX workspace.project_structure_relationship_candidates_profile_source_idx")
    op.execute("DROP INDEX workspace.project_structure_node_versions_profile_locator_idx")
    op.execute("DROP INDEX workspace.project_reconciliation_defects_profile_idx")
    op.execute(
        "ALTER TABLE workspace.project_reconciliation_defects "
        "DROP COLUMN extraction_profile_version"
    )
    op.execute(
        "ALTER TABLE workspace.project_structure_relationship_candidates "
        "DROP COLUMN extraction_profile_version"
    )
    op.execute(
        "ALTER TABLE workspace.project_structure_node_versions "
        "DROP COLUMN extraction_profile_version"
    )
