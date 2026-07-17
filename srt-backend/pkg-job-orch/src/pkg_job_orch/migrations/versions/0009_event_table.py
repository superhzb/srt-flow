"""Replace funnel_events with the generic analytics event table.

Prototype: no data preserved. Drops ``funnel_events`` outright and adds
``event`` with a UNIQUE ``dedup_key`` for at-most-once keyed emission.

Revision ID: 0009_event_table
Revises: 0008_ledger_receipt_url
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009_event_table"
down_revision: str | None = "0008_ledger_receipt_url"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    for column in ("user_id", "event_type", "created_at"):
        op.drop_index(f"ix_funnel_events_{column}", table_name="funnel_events")
    op.drop_table("funnel_events")

    op.create_table(
        "event",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("event_type", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=True),
        sa.Column("anon_id", sa.String(), nullable=True),
        sa.Column("source", sa.String(), nullable=False, server_default="server"),
        sa.Column("session_id", sa.String(), nullable=True),
        sa.Column("dedup_key", sa.String(), nullable=True),
        sa.Column("props", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("dedup_key", name="uq_event_dedup_key"),
    )
    op.create_index("ix_event_event_type", "event", ["event_type"])
    op.create_index("ix_event_user_id", "event", ["user_id"])
    op.create_index("ix_event_created_at", "event", ["created_at"])
    op.create_index("ix_event_type_created_at", "event", ["event_type", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_event_type_created_at", table_name="event")
    op.drop_index("ix_event_created_at", table_name="event")
    op.drop_index("ix_event_user_id", table_name="event")
    op.drop_index("ix_event_event_type", table_name="event")
    op.drop_table("event")

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
