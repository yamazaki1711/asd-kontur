"""Index successor-to-dependent recovery lookups.

Revision ID: 0052_dependency_success_lookup
Revises: 0051_successor_recovery
"""

from __future__ import annotations

import os

from alembic import op

revision = "0052_dependency_success_lookup"
down_revision = "0051_successor_recovery"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Recovery starts with accepted replacements and needs their terminal
    # dependents. The primary key is ordered by dependent job_id, so it cannot
    # serve this reverse lookup on an immutable history.
    op.execute(
        "CREATE INDEX durable_job_dependencies_success_prerequisite_idx "
        "ON workspace.durable_job_dependencies "
        "(organization_id,workspace_id,depends_on_job_id) "
        "WHERE dependency_kind='success_required'"
    )


def downgrade() -> None:
    if os.environ.get("ASD_ALLOW_DESTRUCTIVE_DOWNGRADE") != "1":
        raise RuntimeError("Dependency lookup index downgrade requires a disposable database")
    op.execute("DROP INDEX workspace.durable_job_dependencies_success_prerequisite_idx")
