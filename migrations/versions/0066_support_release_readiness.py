"""Expose bounded platform catalog inputs to the operator readiness projection.

Revision ID: 0066_support_release_readiness
Revises: 0065_project_field_candidate_bridge
"""

from __future__ import annotations

from alembic import op

revision = "0066_support_release_readiness"
down_revision = "0065_project_field_candidate_bridge"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("GRANT SELECT ON platform.work_types,platform.work_type_versions TO asd_app")


def downgrade() -> None:
    op.execute("REVOKE SELECT ON platform.work_types,platform.work_type_versions FROM asd_app")
