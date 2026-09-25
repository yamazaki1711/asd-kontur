"""Persist durable Qwen reconciliation of extracted construction works.

Revision ID: 0067_project_work_reconciliation
Revises: 0066_support_release_readiness
"""

from __future__ import annotations

import os

from alembic import op

revision = "0067_project_work_reconciliation"
down_revision = "0066_support_release_readiness"
branch_labels = None
depends_on = None

_JOB_KINDS = (
    "DOCUMENT_ADMISSION",
    "DOCUMENT_HASH",
    "PDF_INVENTORY",
    "NATIVE_TEXT_EXTRACTION",
    "DOCUMENT_FORMAT_INVENTORY",
    "PDF_PAGE_HEALTH_ANALYSIS",
    "NATIVE_LAYOUT_EXTRACTION",
    "OCR_ROUTING",
    "OCR_EXTRACTION",
    "DOCUMENT_PAGE_CLASSIFICATION",
    "DOCUMENT_AGGREGATION",
    "PROJECT_DEFINITION_EXTRACTION",
    "WORK_QUANTITY_MATERIAL_EXTRACTION",
    "WORK_PACKAGE_ASSEMBLY",
    "REQUIREMENT_MATRIX_ASSEMBLY",
    "PROJECT_UNDERSTANDING_RECONCILIATION",
    "PROJECT_STRUCTURE_RECONCILIATION",
    "PROJECT_WORK_RECONCILIATION",
    "ID_DOCUMENT_GENERATION",
    "EVIDENCE_INDEX_UPDATE",
    "WORKSPACE_RESET_RECONCILIATION",
)


def _job_kind_constraint(kinds: tuple[str, ...]) -> str:
    return "CHECK (job_kind IN (" + ",".join(repr(value) for value in kinds) + "))"


def upgrade() -> None:
    op.execute("ALTER TABLE workspace.durable_jobs DROP CONSTRAINT durable_jobs_job_kind_check")
    op.execute(
        "ALTER TABLE workspace.durable_jobs ADD CONSTRAINT durable_jobs_job_kind_check "
        + _job_kind_constraint(_JOB_KINDS)
    )
    op.execute(
        """
        CREATE TABLE workspace.project_work_reconciliation_results (
            organization_id uuid NOT NULL,
            workspace_id uuid NOT NULL,
            job_id uuid NOT NULL,
            profile_version text NOT NULL CHECK (profile_version='qwen-project-work-reconciliation-v1'),
            input_digest text NOT NULL CHECK (input_digest ~ '^sha256:[a-f0-9]{64}$'),
            result_manifest jsonb NOT NULL,
            result_digest text NOT NULL CHECK (result_digest ~ '^sha256:[a-f0-9]{64}$'),
            model_identity text NOT NULL,
            recorded_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (organization_id, workspace_id, job_id),
            FOREIGN KEY (organization_id,workspace_id,job_id)
                REFERENCES workspace.durable_jobs(organization_id,workspace_id,job_id)
                ON DELETE RESTRICT
        )
        """
    )
    op.execute(
        "CREATE INDEX project_work_reconciliation_results_profile_idx ON "
        "workspace.project_work_reconciliation_results "
        "(organization_id,workspace_id,profile_version,recorded_at)"
    )
    op.execute(
        "ALTER TABLE workspace.project_work_reconciliation_results ENABLE ROW LEVEL SECURITY"
    )
    op.execute(
        "ALTER TABLE workspace.project_work_reconciliation_results FORCE ROW LEVEL SECURITY"
    )
    op.execute(
        "CREATE POLICY project_work_reconciliation_results_scope ON "
        "workspace.project_work_reconciliation_results USING ("
        "organization_id=NULLIF(current_setting('asd.organization_id',true),'')::uuid AND "
        "workspace_id=NULLIF(current_setting('asd.workspace_id',true),'')::uuid) WITH CHECK ("
        "organization_id=NULLIF(current_setting('asd.organization_id',true),'')::uuid AND "
        "workspace_id=NULLIF(current_setting('asd.workspace_id',true),'')::uuid)"
    )
    op.execute("GRANT SELECT ON workspace.project_work_reconciliation_results TO asd_app")
    op.execute(
        "GRANT SELECT,INSERT ON workspace.project_work_reconciliation_results TO asd_document_worker"
    )
    op.execute(
        "GRANT SELECT,DELETE ON workspace.project_work_reconciliation_results "
        "TO asd_destruction_executor"
    )
    op.execute(
        "CREATE TRIGGER project_work_reconciliation_results_immutable BEFORE UPDATE OR DELETE ON "
        "workspace.project_work_reconciliation_results FOR EACH ROW EXECUTE FUNCTION "
        "application.reject_spine_mutation_except_destruction()"
    )


def downgrade() -> None:
    if os.environ.get("ASD_ALLOW_DESTRUCTIVE_DOWNGRADE") != "1":
        raise RuntimeError("Project work reconciliation downgrade requires a disposable database")
    op.execute("DROP TABLE workspace.project_work_reconciliation_results")
    prior = tuple(value for value in _JOB_KINDS if value != "PROJECT_WORK_RECONCILIATION")
    op.execute("ALTER TABLE workspace.durable_jobs DROP CONSTRAINT durable_jobs_job_kind_check")
    op.execute(
        "ALTER TABLE workspace.durable_jobs ADD CONSTRAINT durable_jobs_job_kind_check "
        + _job_kind_constraint(prior)
    )
