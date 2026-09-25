"""Index evidence hydration by scoped source locator.

Revision ID: 0061_native_layout_locator_index
Revises: 0060_current_package_memberships
"""

from __future__ import annotations

import os

from alembic import op

revision = "0061_native_layout_locator_index"
down_revision = "0060_current_package_memberships"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "native_layout_element_versions_locator_version_idx",
        "native_layout_element_versions",
        ["organization_id", "workspace_id", "source_locator_id", "version"],
        schema="workspace",
    )


def downgrade() -> None:
    if os.environ.get("ASD_ALLOW_DESTRUCTIVE_DOWNGRADE") != "1":
        raise RuntimeError("Native-layout locator-index downgrade requires a disposable database")
    op.drop_index(
        "native_layout_element_versions_locator_version_idx",
        table_name="native_layout_element_versions",
        schema="workspace",
    )
