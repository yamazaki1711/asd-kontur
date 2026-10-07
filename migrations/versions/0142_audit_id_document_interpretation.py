"""Allow supervised, source-scoped interpretation of uploaded ID documents.

Revision ID: 0142_audit_id_document_interpretation
Revises: 0141_contract_reference_partial_package
"""

from __future__ import annotations

import os

import sqlalchemy as sa
from alembic import op

revision = "0142_audit_id_document_interpretation"
down_revision = "0141_contract_reference_partial_package"
branch_labels = None
depends_on = None

_KIND = "AUDIT_ID_DOCUMENT_INTERPRETATION"
_MODEL_KINDS = (
    "'PROJECT_WORK_RECONCILIATION','CONTRACT_ANALYSIS','CONTRACT_REFERENCE_REVIEW',"
    "'CONTRACT_COHERENCE_REVIEW'"
)


def _job_constraint(*, include: bool) -> str:
    definition = op.get_bind().scalar(
        sa.text(
            "SELECT pg_get_constraintdef(oid) FROM pg_constraint WHERE "
            "conrelid='workspace.durable_jobs'::regclass "
            "AND conname='durable_jobs_job_kind_check'"
        )
    )
    if not isinstance(definition, str):
        raise RuntimeError("job-kind constraint unavailable")
    entry = f"'{_KIND}'::text"
    if include:
        if entry in definition:
            return definition
        end = definition.rfind("]")
        if end < 0:
            raise RuntimeError("job-kind constraint shape unavailable")
        return definition[:end] + f", {entry}" + definition[end:]
    return definition.replace(f", {entry}", "")


def _replace_constraint(definition: str) -> None:
    op.execute("ALTER TABLE workspace.durable_jobs DROP CONSTRAINT durable_jobs_job_kind_check")
    op.execute(
        "ALTER TABLE workspace.durable_jobs ADD CONSTRAINT durable_jobs_job_kind_check "
        + definition
    )


def _replace_fairness(source: str, target: str) -> None:
    definition = op.get_bind().scalar(
        sa.text(
            "SELECT pg_get_functiondef("
            "'workspace.claim_next_durable_job(text,integer)'::regprocedure)"
        )
    )
    if not isinstance(definition, str) or source not in definition:
        raise RuntimeError("model-slot fairness definition unavailable")
    op.get_bind().execute(sa.text(definition.replace(source, target)))


def upgrade() -> None:
    _replace_constraint(_job_constraint(include=True))
    _replace_fairness(
        "j.job_kind IN ('CONTRACT_ANALYSIS','CONTRACT_REFERENCE_REVIEW',"
        "'CONTRACT_COHERENCE_REVIEW') THEN 3",
        "j.job_kind IN ('CONTRACT_ANALYSIS','CONTRACT_REFERENCE_REVIEW',"
        "'CONTRACT_COHERENCE_REVIEW','AUDIT_ID_DOCUMENT_INTERPRETATION') THEN 3",
    )
    _replace_fairness(_MODEL_KINDS, _MODEL_KINDS + ",'AUDIT_ID_DOCUMENT_INTERPRETATION'")


def downgrade() -> None:
    if os.environ.get("ASD_ALLOW_DESTRUCTIVE_DOWNGRADE") != "1":
        raise RuntimeError("Audit interpretation downgrade requires a disposable database")
    if op.get_bind().scalar(
        sa.text("SELECT EXISTS (SELECT 1 FROM workspace.durable_jobs WHERE job_kind=:kind)"),
        {"kind": _KIND},
    ):
        raise RuntimeError("Audit interpretation jobs exist; downgrade requires a clean fixture")
    _replace_fairness(_MODEL_KINDS + ",'AUDIT_ID_DOCUMENT_INTERPRETATION'", _MODEL_KINDS)
    _replace_fairness(
        "j.job_kind IN ('CONTRACT_ANALYSIS','CONTRACT_REFERENCE_REVIEW',"
        "'CONTRACT_COHERENCE_REVIEW','AUDIT_ID_DOCUMENT_INTERPRETATION') THEN 3",
        "j.job_kind IN ('CONTRACT_ANALYSIS','CONTRACT_REFERENCE_REVIEW',"
        "'CONTRACT_COHERENCE_REVIEW') THEN 3",
    )
    _replace_constraint(_job_constraint(include=False))
