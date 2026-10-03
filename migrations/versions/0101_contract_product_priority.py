"""Prioritize autonomous contract results before long-tail model work.

Revision ID: 0101_contract_product_priority
Revises: 0100_contract_row_context
"""

from __future__ import annotations

import os

import sqlalchemy as sa
from alembic import op

revision = "0101_contract_product_priority"
down_revision = "0100_contract_row_context"
branch_labels = None
depends_on = None

_CURRENT_ORDER_START = """ORDER BY
             CASE WHEN ("""

_PRODUCT_ORDER_START = """ORDER BY
             CASE WHEN j.job_kind='CONTRACT_ANALYSIS' THEN 3
             WHEN ("""


def _replace_order(source: str, target: str) -> None:
    connection = op.get_bind()
    definition = connection.scalar(
        sa.text(
            "SELECT pg_get_functiondef("
            "'workspace.claim_next_durable_job(text,integer)'::regprocedure)"
        )
    )
    if not isinstance(definition, str) or source not in definition:
        raise RuntimeError("durable-job product-priority ordering unavailable")
    connection.execute(sa.text(definition.replace(source, target, 1)))


def upgrade() -> None:
    """Deliver admitted contract analysis before lower-value semantic backlog."""

    _replace_order(_CURRENT_ORDER_START, _PRODUCT_ORDER_START)


def downgrade() -> None:
    if os.environ.get("ASD_ALLOW_DESTRUCTIVE_DOWNGRADE") != "1":
        raise RuntimeError("Contract-priority downgrade requires a disposable database")
    _replace_order(_PRODUCT_ORDER_START, _CURRENT_ORDER_START)
