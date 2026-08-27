"""Allow supervised runtime roles to report the exact migration head.

Revision ID: 0027_public_deployment
Revises: 0026_support_id_finalize
Create Date: 2026-08-27
"""

from __future__ import annotations

import os

from alembic import op

revision = "0027_public_deployment"
down_revision = "0026_support_id_finalize"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "GRANT SELECT ON TABLE alembic_version TO asd_app,asd_document_worker,"
        "asd_lifecycle_service,asd_destruction_executor"
    )


def downgrade() -> None:
    if os.environ.get("ASD_ALLOW_DESTRUCTIVE_DOWNGRADE") != "1":
        raise RuntimeError("Public deployment runtime downgrade requires a disposable database")
    op.execute(
        "REVOKE SELECT ON TABLE alembic_version FROM asd_app,asd_document_worker,"
        "asd_lifecycle_service,asd_destruction_executor"
    )
