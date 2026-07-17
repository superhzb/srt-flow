"""Add the optional display filename to jobs.

Revision ID: 0004_job_filename
Revises: 0003_job_debug_fields
Create Date: 2026-07-10
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004_job_filename"
down_revision: str | None = "0003_job_debug_fields"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("job", sa.Column("filename", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("job", "filename")
