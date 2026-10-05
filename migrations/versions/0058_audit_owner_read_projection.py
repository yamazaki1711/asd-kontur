"""Expose immutable Audit report projections to the authorized workspace owner.

Revision ID: 0058_audit_owner_read_projection
Revises: 0057_audit_report_action_request_memberships
"""

from __future__ import annotations

import os

from alembic import op

revision = "0058_audit_owner_read_projection"
down_revision = "0057_audit_report_action_request_memberships"
branch_labels = None
depends_on = None

_PREDICATE = """
organization_id = nullif(current_setting('asd.organization_id',true),'')::uuid
AND workspace_id = nullif(current_setting('asd.workspace_id',true),'')::uuid
"""


def upgrade() -> None:
    """Grant only scoped SELECT over already-immutable projection rows.

    The application role receives no Audit-ledger write privilege.  Projection
    rows are created in the same transaction as an Audit report by the
    separately scoped Audit service.
    """

    op.execute(
        "CREATE POLICY audit_projection_versions_application_read_scope_policy "
        "ON workspace.audit_projection_versions FOR SELECT TO asd_app USING (" + _PREDICATE + ")"
    )
    op.execute("GRANT SELECT ON workspace.audit_projection_versions TO asd_app")


def downgrade() -> None:
    if os.environ.get("ASD_ALLOW_DESTRUCTIVE_DOWNGRADE") != "1":
        raise RuntimeError("Audit owner-read projection downgrade requires a disposable database")
    op.execute(
        "DROP POLICY audit_projection_versions_application_read_scope_policy ON workspace.audit_projection_versions"
    )
    op.execute("REVOKE SELECT ON workspace.audit_projection_versions FROM asd_app")
