"""Add per-target job progress.

Revision ID: 0005_job_target_progress
Revises: 0004_job_filename
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005_job_target_progress"
down_revision: str | None = "0004_job_filename"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("job", sa.Column("progress_by_target", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("job", "progress_by_target")
