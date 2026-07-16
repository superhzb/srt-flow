"""Add pre-supplied carried languages to jobs.

Revision ID: 0007_job_carried_langs
Revises: 0006_credit_ledger
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007_job_carried_langs"
down_revision: str | None = "0006_credit_ledger"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("job", sa.Column("carried_langs", sa.String(), nullable=False, server_default=""))


def downgrade() -> None:
    op.drop_column("job", "carried_langs")
