"""Add durable job failure-detail fields.

Adds two nullable columns for debuggable hard failures:
- ``error_detail`` — exception class + repr captured at the raise site.
- ``failed_target`` — target language in flight when the job hard-failed.

Revision ID: 0010_job_failure_detail
Revises: 0009_event_table
Create Date: 2026-07-18
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0010_job_failure_detail"
down_revision: str | None = "0009_event_table"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("job", sa.Column("error_detail", sa.String(), nullable=True))
    op.add_column("job", sa.Column("failed_target", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("job", "failed_target")
    op.drop_column("job", "error_detail")
