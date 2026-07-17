"""Add minute balances, source duration, and the append-only credit ledger.

Revision ID: 0006_credit_ledger
Revises: 0005_job_target_progress
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006_credit_ledger"
down_revision: str | None = "0005_job_target_progress"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("user") as batch_op:
        batch_op.add_column(
            sa.Column("purchased_minutes", sa.Integer(), nullable=False, server_default="0")
        )
    # The old paid tier was an unlimited bypass. Existing rows are prototype
    # users, so explicitly return every account to the free minute model.
    op.execute(sa.text("UPDATE user SET tier = 'free'"))

    op.add_column(
        "job", sa.Column("source_minutes", sa.Integer(), nullable=False, server_default="0")
    )
    with op.batch_alter_table("processed_events") as batch_op:
        batch_op.create_unique_constraint("uq_processed_events_session_id", ["session_id"])

    op.create_table(
        "credit_ledger",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("entry_type", sa.String(), nullable=False),
        sa.Column("minutes_delta", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("balance_after", sa.Integer(), nullable=True),
        sa.Column("usage_minutes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("usage_month", sa.String(), nullable=True),
        sa.Column("idempotency_key", sa.String(), nullable=False),
        sa.Column("session_id", sa.String(), nullable=True),
        sa.Column("event_id", sa.String(), nullable=True),
        sa.Column("job_id", sa.String(), nullable=True),
        sa.Column("pack", sa.String(), nullable=True),
        sa.Column("amount_cents", sa.Integer(), nullable=True),
        sa.Column("currency", sa.String(), nullable=True),
        sa.Column("payment_intent_id", sa.String(), nullable=True),
        sa.Column("charge_id", sa.String(), nullable=True),
        sa.Column("reason", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("idempotency_key", name="uq_credit_ledger_idempotency_key"),
        sa.UniqueConstraint("session_id", name="uq_credit_ledger_session_id"),
        sa.UniqueConstraint("job_id", name="uq_credit_ledger_job_id"),
    )
    ledger_indexes = (
        "user_id",
        "entry_type",
        "balance_after",
        "usage_month",
        "payment_intent_id",
        "charge_id",
        "created_at",
    )
    for column in ledger_indexes:
        op.create_index(f"ix_credit_ledger_{column}", "credit_ledger", [column])

    op.create_table(
        "funnel_events",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("event_type", sa.String(), nullable=False),
        sa.Column("pack", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in ("user_id", "event_type", "created_at"):
        op.create_index(f"ix_funnel_events_{column}", "funnel_events", [column])


def downgrade() -> None:
    op.drop_table("funnel_events")
    op.drop_table("credit_ledger")
    with op.batch_alter_table("processed_events") as batch_op:
        batch_op.drop_constraint("uq_processed_events_session_id", type_="unique")
    op.drop_column("job", "source_minutes")
    op.drop_column("user", "purchased_minutes")
