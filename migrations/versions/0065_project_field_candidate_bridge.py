"""Bridge document-worker project fields into the confirmed-fact candidate kernel.

Revision ID: 0065_project_field_candidate_bridge
Revises: 0064_pit_observation_disposition_receipts
"""

from __future__ import annotations

from alembic import op

revision = "0065_project_field_candidate_bridge"
down_revision = "0064_pit_observation_disposition_receipts"
branch_labels = None
depends_on = None

_CANDIDATE_TABLES = (
    "candidates",
    "candidate_versions",
    "candidate_fields",
    "candidate_field_evidence",
    "vlm_validation_runs",
)


def upgrade() -> None:
    predicate = (
        "organization_id=NULLIF(current_setting('asd.organization_id',true),'')::uuid AND "
        "workspace_id=NULLIF(current_setting('asd.workspace_id',true),'')::uuid"
    )
    for table in _CANDIDATE_TABLES:
        op.execute(
            f"CREATE POLICY {table}_document_worker_bridge_scope ON workspace.{table} "
            f"FOR ALL TO asd_document_worker USING ({predicate}) WITH CHECK ({predicate})"
        )
        op.execute(f"GRANT SELECT,INSERT ON workspace.{table} TO asd_document_worker")
    op.execute(
        "CREATE POLICY evidence_links_document_worker_bridge_scope ON workspace.evidence_links "
        f"FOR ALL TO asd_document_worker USING ({predicate}) WITH CHECK ({predicate})"
    )
    op.execute("GRANT SELECT,INSERT ON workspace.evidence_links TO asd_document_worker")
    op.execute("GRANT SELECT ON workspace.project_field_candidates TO asd_kernel_service")
    op.execute(
        """
        CREATE TABLE workspace.support_field_candidate_decisions (
          organization_id uuid NOT NULL,
          workspace_id uuid NOT NULL,
          decision_id uuid NOT NULL,
          decision_version bigint NOT NULL CHECK (decision_version>=1),
          work_package_id uuid NOT NULL,
          work_package_version bigint NOT NULL,
          target_field_key text NOT NULL,
          candidate_id uuid NOT NULL,
          from_candidate_version bigint NOT NULL,
          to_candidate_version bigint NOT NULL,
          action text NOT NULL CHECK (action IN ('corrected')),
          actor_identity_id text NOT NULL,
          reason text NOT NULL CHECK (length(reason)>=3),
          decision_digest text NOT NULL CHECK (decision_digest ~ '^sha256:[a-f0-9]{64}$'),
          decided_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
          PRIMARY KEY (organization_id,workspace_id,decision_id,decision_version),
          UNIQUE (organization_id,workspace_id,candidate_id,to_candidate_version),
          FOREIGN KEY (organization_id,workspace_id,candidate_id,from_candidate_version)
            REFERENCES workspace.candidate_versions
              (organization_id,workspace_id,candidate_id,candidate_version) ON DELETE RESTRICT,
          FOREIGN KEY (organization_id,workspace_id,candidate_id,to_candidate_version)
            REFERENCES workspace.candidate_versions
              (organization_id,workspace_id,candidate_id,candidate_version) ON DELETE RESTRICT,
          FOREIGN KEY (organization_id,workspace_id,work_package_id,work_package_version)
            REFERENCES workspace.construction_work_package_versions
              (organization_id,workspace_id,work_package_id,version) ON DELETE RESTRICT
        );
        ALTER TABLE workspace.support_field_candidate_decisions ENABLE ROW LEVEL SECURITY;
        ALTER TABLE workspace.support_field_candidate_decisions FORCE ROW LEVEL SECURITY;
        """
    )
    op.execute(
        "CREATE POLICY support_field_candidate_decisions_app_scope ON "
        "workspace.support_field_candidate_decisions FOR SELECT TO asd_app "
        f"USING ({predicate})"
    )
    op.execute(
        "CREATE POLICY support_field_candidate_decisions_harness_scope ON "
        "workspace.support_field_candidate_decisions FOR ALL TO asd_harness_service "
        f"USING ({predicate}) WITH CHECK ({predicate})"
    )
    op.execute(
        "CREATE POLICY support_field_candidate_decisions_destruction_scope ON "
        "workspace.support_field_candidate_decisions FOR ALL TO asd_destruction_executor "
        f"USING ({predicate}) WITH CHECK ({predicate})"
    )
    op.execute("GRANT SELECT ON workspace.support_field_candidate_decisions TO asd_app")
    op.execute(
        "GRANT SELECT,INSERT ON workspace.support_field_candidate_decisions TO asd_harness_service"
    )
    op.execute(
        "GRANT SELECT,DELETE ON workspace.support_field_candidate_decisions "
        "TO asd_destruction_executor"
    )
    op.execute(
        "CREATE TRIGGER support_field_candidate_decisions_immutable BEFORE UPDATE OR DELETE ON "
        "workspace.support_field_candidate_decisions FOR EACH ROW EXECUTE FUNCTION "
        "workspace.reject_harness_mutation_unless_destroy()"
    )


def downgrade() -> None:
    op.execute("DROP TABLE workspace.support_field_candidate_decisions")
    op.execute("REVOKE SELECT ON workspace.project_field_candidates FROM asd_kernel_service")
    op.execute("REVOKE SELECT,INSERT ON workspace.evidence_links FROM asd_document_worker")
    op.execute(
        "DROP POLICY IF EXISTS evidence_links_document_worker_bridge_scope "
        "ON workspace.evidence_links"
    )
    for table in reversed(_CANDIDATE_TABLES):
        op.execute(f"REVOKE SELECT,INSERT ON workspace.{table} FROM asd_document_worker")
        op.execute(
            f"DROP POLICY IF EXISTS {table}_document_worker_bridge_scope ON workspace.{table}"
        )
