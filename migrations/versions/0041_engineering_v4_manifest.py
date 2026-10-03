"""Require fragment provenance for v4 engineering extraction.

Revision ID: 0041_engineering_v4_manifest
Revises: 0040_engineering_fragments
"""

from __future__ import annotations

import os

from alembic import op

revision = "0041_engineering_v4_manifest"
down_revision = "0040_engineering_fragments"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE workspace.engineering_extraction_batches DROP CONSTRAINT "
        "engineering_extraction_batches_v3_input_manifest"
    )
    op.execute(
        "ALTER TABLE workspace.engineering_extraction_batches ADD CONSTRAINT "
        "engineering_extraction_batches_v3_v4_input_manifest CHECK ("
        "profile_version NOT IN ('qwen-engineering-extraction-v3',"
        "'qwen-engineering-extraction-v4') OR input_manifest IS NOT NULL)"
    )


def downgrade() -> None:
    if os.environ.get("ASD_ALLOW_DESTRUCTIVE_DOWNGRADE") != "1":
        raise RuntimeError("Engineering batch provenance downgrade requires a disposable database")
    op.execute(
        "ALTER TABLE workspace.engineering_extraction_batches DROP CONSTRAINT "
        "engineering_extraction_batches_v3_v4_input_manifest"
    )
    op.execute(
        "ALTER TABLE workspace.engineering_extraction_batches ADD CONSTRAINT "
        "engineering_extraction_batches_v3_input_manifest CHECK ("
        "profile_version <> 'qwen-engineering-extraction-v3' OR input_manifest IS NOT NULL)"
    )
