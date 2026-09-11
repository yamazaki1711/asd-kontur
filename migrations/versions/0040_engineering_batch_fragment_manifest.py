"""Record immutable fragment provenance for engineering extraction batches.

Revision ID: 0040_engineering_fragments
Revises: 0039_engineering_batches
"""

from __future__ import annotations

import os

from alembic import op

revision = "0040_engineering_fragments"
down_revision = "0039_engineering_batches"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE workspace.engineering_extraction_batches ADD COLUMN input_manifest jsonb"
    )
    op.execute(
        "ALTER TABLE workspace.engineering_extraction_batches ADD CONSTRAINT "
        "engineering_extraction_batches_v3_input_manifest CHECK ("
        "profile_version <> 'qwen-engineering-extraction-v3' OR input_manifest IS NOT NULL)"
    )


def downgrade() -> None:
    if os.environ.get("ASD_ALLOW_DESTRUCTIVE_DOWNGRADE") != "1":
        raise RuntimeError("Engineering batch provenance downgrade requires a disposable database")
    op.execute(
        "ALTER TABLE workspace.engineering_extraction_batches DROP CONSTRAINT "
        "engineering_extraction_batches_v3_input_manifest"
    )
    op.execute("ALTER TABLE workspace.engineering_extraction_batches DROP COLUMN input_manifest")
