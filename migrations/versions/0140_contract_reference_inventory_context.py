"""Permit source-context contract-reference reviews without rewriting v1 history.

Revision ID: 0140_contract_reference_inventory_context
Revises: 0139_field_document_project_role_boundary
"""

from __future__ import annotations

import os

import sqlalchemy as sa
from alembic import op

revision = "0140_contract_reference_inventory_context"
down_revision = "0139_field_document_project_role_boundary"
branch_labels = None
depends_on = None

_CONSTRAINT = "contract_analysis_results_profile_version_check"
_PROFILE = "qwen-contract-references-v2"


def _definition(*, include: bool) -> str:
    definition = op.get_bind().scalar(
        sa.text(
            "SELECT pg_get_constraintdef(oid) FROM pg_constraint WHERE "
            "conrelid='workspace.contract_analysis_results'::regclass AND conname=:name"
        ),
        {"name": _CONSTRAINT},
    )
    if not isinstance(definition, str):
        raise RuntimeError("contract analysis result profile constraint unavailable")
    entry = f"'{_PROFILE}'::text"
    if include:
        if entry in definition:
            return definition
        array_end = definition.rfind("]")
        if array_end < 0:
            raise RuntimeError("contract analysis result profile constraint shape unavailable")
        return definition[:array_end] + f", {entry}" + definition[array_end:]
    if entry not in definition:
        return definition
    return definition.replace(f", {entry}", "")


def _replace_constraint(definition: str) -> None:
    op.execute(f"ALTER TABLE workspace.contract_analysis_results DROP CONSTRAINT {_CONSTRAINT}")
    op.execute(
        f"ALTER TABLE workspace.contract_analysis_results ADD CONSTRAINT {_CONSTRAINT} "
        + definition
    )


def upgrade() -> None:
    _replace_constraint(_definition(include=True))


def downgrade() -> None:
    if os.environ.get("ASD_ALLOW_DESTRUCTIVE_DOWNGRADE") != "1":
        raise RuntimeError("Contract-reference profile downgrade requires a disposable database")
    persisted = op.get_bind().scalar(
        sa.text(
            "SELECT EXISTS (SELECT 1 FROM workspace.contract_analysis_results "
            "WHERE profile_version=:profile)"
        ),
        {"profile": _PROFILE},
    )
    if persisted:
        raise RuntimeError(
            "v2 contract-reference results exist; downgrade requires a clean fixture"
        )
    _replace_constraint(_definition(include=False))
