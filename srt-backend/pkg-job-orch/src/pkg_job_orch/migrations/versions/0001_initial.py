"""slice-3 initial schema: user + job.

Revision ID: 0001_initial
Revises:
Create Date: 2026-07-08

Two tables per PLAN.md slice 3:
  - user: one seeded dev row (google_sub arrives in slice 4 via 0002).
  - job: one row per upload → N targets. tgt_langs is CSV; output paths
    are derived ({job_id}/output.<lang>.srt), not stored.

Engine: SQLite. ``render_as_batch=True`` in env.py keeps ALTERs working
under SQLite's limited DDL.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001_initial"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "user",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("email", sa.String(), nullable=False),
        sa.Column("tier", sa.String(), nullable=False, server_default="free"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "job",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default="pending"),
        sa.Column("worker", sa.String(), nullable=False),
        sa.Column("src_lang", sa.String(), nullable=False),
        sa.Column("tgt_langs", sa.String(), nullable=False, server_default=""),
        sa.Column("progress", sa.Float(), nullable=False, server_default="0"),
        sa.Column("error", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"]),
    )
    op.create_index("ix_job_user_id", "job", ["user_id"])
    op.create_index("ix_job_status", "job", ["status"])


def downgrade() -> None:
    op.drop_index("ix_job_status", table_name="job")
    op.drop_index("ix_job_user_id", table_name="job")
    op.drop_table("job")
    op.drop_table("user")
