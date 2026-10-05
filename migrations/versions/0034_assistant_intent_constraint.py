"""Assistant intent constraint migration."""

from alembic import op

revision = "0034_assistant_intent_constraint"
down_revision = "0033_ntd_memory"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint(
        "assistant_quality_receipts_intent_check",
        "assistant_quality_receipts",
        schema="workspace",
        type_="check",
    )
    op.create_check_constraint(
        "assistant_quality_receipts_intent_check",
        "assistant_quality_receipts",
        "intent IN ('general_engineering', 'normative', 'workspace', 'mixed', 'clarification_required')",
        schema="workspace",
    )


def downgrade() -> None:
    op.drop_constraint(
        "assistant_quality_receipts_intent_check",
        "assistant_quality_receipts",
        schema="workspace",
        type_="check",
    )
    op.execute(
        "UPDATE workspace.assistant_quality_receipts SET intent = 'general' WHERE intent = 'general_engineering'"
    )
    op.execute(
        "UPDATE workspace.assistant_quality_receipts SET intent = 'ambiguous' WHERE intent IN ('normative', 'clarification_required')"
    )
    op.create_check_constraint(
        "assistant_quality_receipts_intent_check",
        "assistant_quality_receipts",
        "intent IN ('general', 'workspace', 'mixed', 'ambiguous')",
        schema="workspace",
    )
