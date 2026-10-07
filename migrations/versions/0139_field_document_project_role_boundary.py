"""Let the document worker read workspace-scoped source roles for scheduling.

Revision ID: 0139_field_document_project_role_boundary
Revises: 0138_support_material_use_evidence
"""

from __future__ import annotations

from alembic import op

revision = "0139_field_document_project_role_boundary"
down_revision = "0138_support_material_use_evidence"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("GRANT SELECT ON workspace.source_artifacts TO asd_document_worker")
    op.execute(
        "CREATE POLICY source_artifacts_document_worker_read ON workspace.source_artifacts "
        "FOR SELECT TO asd_document_worker USING ("
        "organization_id=NULLIF(current_setting('asd.organization_id',true),'')::uuid "
        "AND workspace_id=NULLIF(current_setting('asd.workspace_id',true),'')::uuid)"
    )


def downgrade() -> None:
    op.execute("DROP POLICY source_artifacts_document_worker_read ON workspace.source_artifacts")
    op.execute("REVOKE SELECT ON workspace.source_artifacts FROM asd_document_worker")
