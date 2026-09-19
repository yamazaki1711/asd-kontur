"""Permit the durable reconciliation job implemented by the current worker.

Revision ID: 0050_project_structure_reconciliation_job
Revises: 0049_structure_identity_candidates
"""

from __future__ import annotations

from alembic import op

revision = "0050_project_structure_reconciliation_job"
down_revision = "0049_structure_identity_candidates"
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
    "ID_DOCUMENT_GENERATION",
    "EVIDENCE_INDEX_UPDATE",
    "WORKSPACE_RESET_RECONCILIATION",
)


def _job_kind_constraint(kinds: tuple[str, ...]) -> str:
    quoted = ",".join(repr(value) for value in kinds)
    return f"CHECK (job_kind IN ({quoted}))"


def upgrade() -> None:
    op.execute("ALTER TABLE workspace.durable_jobs DROP CONSTRAINT durable_jobs_job_kind_check")
    op.execute(
        "ALTER TABLE workspace.durable_jobs ADD CONSTRAINT durable_jobs_job_kind_check "
        + _job_kind_constraint(_JOB_KINDS)
    )


def downgrade() -> None:
    prior_kinds = tuple(kind for kind in _JOB_KINDS if kind != "PROJECT_STRUCTURE_RECONCILIATION")
    op.execute("ALTER TABLE workspace.durable_jobs DROP CONSTRAINT durable_jobs_job_kind_check")
    op.execute(
        "ALTER TABLE workspace.durable_jobs ADD CONSTRAINT durable_jobs_job_kind_check "
        + _job_kind_constraint(prior_kinds)
    )
