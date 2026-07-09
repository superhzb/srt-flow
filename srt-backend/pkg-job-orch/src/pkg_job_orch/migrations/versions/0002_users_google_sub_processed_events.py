"""durable auth users and processed Stripe events.

Revision ID: 0002_users_google_sub_processed_events
Revises: 0001_initial
Create Date: 2026-07-09
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002_users_google_sub_processed_events"
down_revision: str | None = "0001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("user") as batch_op:
        batch_op.add_column(sa.Column("google_sub", sa.String(), nullable=True))
        batch_op.create_unique_constraint("uq_user_google_sub", ["google_sub"])

    op.create_table(
        "processed_events",
        sa.Column("event_id", sa.String(), nullable=False),
        sa.Column("session_id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("paid_at", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"]),
        sa.PrimaryKeyConstraint("event_id"),
    )
    op.create_index("ix_processed_events_user_id", "processed_events", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_processed_events_user_id", table_name="processed_events")
    op.drop_table("processed_events")
    with op.batch_alter_table("user") as batch_op:
        batch_op.drop_constraint("uq_user_google_sub", type_="unique")
        batch_op.drop_column("google_sub")
