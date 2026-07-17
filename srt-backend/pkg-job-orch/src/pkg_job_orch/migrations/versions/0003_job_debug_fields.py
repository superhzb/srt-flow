"""Add durable job debugging fields.

Revision ID: 0003_job_debug_fields
Revises: 0002_users_google_sub_processed_events
Create Date: 2026-07-10
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003_job_debug_fields"
down_revision: str | None = "0002_users_google_sub_processed_events"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("job", sa.Column("started_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("job", sa.Column("error_kind", sa.String(), nullable=True))
    op.add_column("job", sa.Column("dropped_by_target", sa.String(), nullable=True))
    op.add_column(
        "job",
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("job", "attempts")
    op.drop_column("job", "dropped_by_target")
    op.drop_column("job", "error_kind")
    op.drop_column("job", "started_at")
