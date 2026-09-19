"""Align canonical Audit process persistence with its declared state machine.

Revision ID: 0054_align_audit_process_state
Revises: 0053_rewire_recovery_edges
"""

from __future__ import annotations

import os

from alembic import op

revision = "0054_align_audit_process_state"
down_revision = "0053_rewire_recovery_edges"
branch_labels = None
depends_on = None

_STATES = (
    "requested",
    "collecting",
    "reconciling",
    "snapshotted",
    "evaluating",
    "blocked",
    "completed",
    "failed",
    "quarantined",
)


def _replace_state_constraint(states: tuple[str, ...]) -> None:
    values = ",".join(f"'{state}'" for state in states)
    op.execute(
        "ALTER TABLE workspace.audit_processes "
        "DROP CONSTRAINT IF EXISTS audit_processes_state_check"
    )
    op.execute(
        "ALTER TABLE workspace.audit_processes "
        "ADD CONSTRAINT audit_processes_state_check "
        f"CHECK (state IN ({values}))"
    )


def upgrade() -> None:
    _replace_state_constraint(_STATES)


def downgrade() -> None:
    if os.environ.get("ASD_ALLOW_DESTRUCTIVE_DOWNGRADE") != "1":
        raise RuntimeError("Audit process state downgrade requires a disposable database")
    _replace_state_constraint(
        ("requested", "evaluating", "blocked", "completed", "failed", "quarantined")
    )
