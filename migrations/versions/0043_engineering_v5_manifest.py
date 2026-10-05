"""Require an object-shaped v5 engineering batch input manifest.

Revision ID: 0043_engineering_v5
Revises: 0042_dependency_recovery
"""

from __future__ import annotations

import os

from alembic import op

revision = "0043_engineering_v5"
down_revision = "0042_dependency_recovery"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE workspace.engineering_extraction_batches ADD CONSTRAINT "
        "engineering_extraction_batches_v5_object_manifest CHECK ("
        "profile_version <> 'qwen-engineering-extraction-v5' OR ("
        "jsonb_typeof(input_manifest)='object' AND "
        "jsonb_typeof(input_manifest->'fragments')='array' AND "
        "jsonb_array_length(input_manifest->'fragments') > 0))"
    )


def downgrade() -> None:
    if os.environ.get("ASD_ALLOW_DESTRUCTIVE_DOWNGRADE") != "1":
        raise RuntimeError("Engineering v5 manifest downgrade requires a disposable database")
    op.execute(
        "ALTER TABLE workspace.engineering_extraction_batches DROP CONSTRAINT "
        "engineering_extraction_batches_v5_object_manifest"
    )
