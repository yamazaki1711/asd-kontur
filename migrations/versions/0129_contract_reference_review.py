"""Add bounded autonomous review of contract attachment references.

Revision ID: 0129_contract_reference_review
Revises: 0128_destroyed_object_redaction
"""

from __future__ import annotations

import os

import sqlalchemy as sa
from alembic import op

revision = "0129_contract_reference_review"
down_revision = "0128_destroyed_object_redaction"
branch_labels = None
depends_on = None

_JOB_KIND = "CONTRACT_REFERENCE_REVIEW"
_PROFILE = "qwen-contract-references-v1"


def _constraint(name: str, table: str, addition: str, *, include: bool) -> str:
    definition = op.get_bind().scalar(
        sa.text(
            "SELECT pg_get_constraintdef(oid) FROM pg_constraint WHERE "
            "conrelid=CAST(:table AS regclass) AND conname=:name"
        ),
        {"table": table, "name": name},
    )
    if not isinstance(definition, str):
        raise RuntimeError(f"constraint unavailable: {name}")
    if include:
        if addition in definition:
            return definition
        array_end = definition.rfind("]")
        if array_end < 0:
            raise RuntimeError(f"constraint shape unavailable: {name}")
        return definition[:array_end] + f", '{addition}'::text" + definition[array_end:]
    return definition.replace(f", '{addition}'::text", "")


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
    job_constraint = _constraint(
        "durable_jobs_job_kind_check", "workspace.durable_jobs", _JOB_KIND, include=True
    )
    op.execute("ALTER TABLE workspace.durable_jobs DROP CONSTRAINT durable_jobs_job_kind_check")
    op.execute(
        "ALTER TABLE workspace.durable_jobs ADD CONSTRAINT durable_jobs_job_kind_check "
        + job_constraint
    )
    profile_constraint = _constraint(
        "contract_analysis_results_profile_version_check",
        "workspace.contract_analysis_results",
        _PROFILE,
        include=True,
    )
    op.execute(
        "ALTER TABLE workspace.contract_analysis_results DROP CONSTRAINT "
        "contract_analysis_results_profile_version_check"
    )
    op.execute(
        "ALTER TABLE workspace.contract_analysis_results ADD CONSTRAINT "
        "contract_analysis_results_profile_version_check " + profile_constraint
    )
    _replace_fairness(
        "j.job_kind='CONTRACT_ANALYSIS' THEN 3",
        "j.job_kind IN ('CONTRACT_ANALYSIS','CONTRACT_REFERENCE_REVIEW') THEN 3",
    )
    _replace_fairness(
        "'PROJECT_WORK_RECONCILIATION','CONTRACT_ANALYSIS'",
        "'PROJECT_WORK_RECONCILIATION','CONTRACT_ANALYSIS','CONTRACT_REFERENCE_REVIEW'",
    )


def downgrade() -> None:
    if os.environ.get("ASD_ALLOW_DESTRUCTIVE_DOWNGRADE") != "1":
        raise RuntimeError("Contract-reference downgrade requires a disposable database")
    present = op.get_bind().scalar(
        sa.text(
            "SELECT EXISTS (SELECT 1 FROM workspace.durable_jobs "
            "WHERE job_kind='CONTRACT_REFERENCE_REVIEW')"
        )
    )
    if present:
        raise RuntimeError("Contract-reference jobs exist; disposable downgrade must start clean")
    _replace_fairness(
        "'PROJECT_WORK_RECONCILIATION','CONTRACT_ANALYSIS','CONTRACT_REFERENCE_REVIEW'",
        "'PROJECT_WORK_RECONCILIATION','CONTRACT_ANALYSIS'",
    )
    _replace_fairness(
        "j.job_kind IN ('CONTRACT_ANALYSIS','CONTRACT_REFERENCE_REVIEW') THEN 3",
        "j.job_kind='CONTRACT_ANALYSIS' THEN 3",
    )
    profile_constraint = _constraint(
        "contract_analysis_results_profile_version_check",
        "workspace.contract_analysis_results",
        _PROFILE,
        include=False,
    )
    op.execute(
        "ALTER TABLE workspace.contract_analysis_results DROP CONSTRAINT "
        "contract_analysis_results_profile_version_check"
    )
    op.execute(
        "ALTER TABLE workspace.contract_analysis_results ADD CONSTRAINT "
        "contract_analysis_results_profile_version_check " + profile_constraint
    )
    job_constraint = _constraint(
        "durable_jobs_job_kind_check", "workspace.durable_jobs", _JOB_KIND, include=False
    )
    op.execute("ALTER TABLE workspace.durable_jobs DROP CONSTRAINT durable_jobs_job_kind_check")
    op.execute(
        "ALTER TABLE workspace.durable_jobs ADD CONSTRAINT durable_jobs_job_kind_check "
        + job_constraint
    )
