from __future__ import annotations

import os

from alembic import op

revision = "0038_consultant_request_id"
down_revision = "0037_construction_consultant"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE platform.construction_consultant_messages ADD COLUMN request_id uuid")
    op.execute(
        "CREATE UNIQUE INDEX construction_consultant_messages_request_role_unique "
        "ON platform.construction_consultant_messages "
        "(organization_id, conversation_id, request_id, role) "
        "WHERE request_id IS NOT NULL"
    )


def downgrade() -> None:
    if os.environ.get("ASD_ALLOW_DESTRUCTIVE_DOWNGRADE") != "1":
        raise RuntimeError("Assistant downgrade requires a disposable database")
    op.execute("DROP INDEX platform.construction_consultant_messages_request_role_unique")
    op.execute("ALTER TABLE platform.construction_consultant_messages DROP COLUMN request_id")
