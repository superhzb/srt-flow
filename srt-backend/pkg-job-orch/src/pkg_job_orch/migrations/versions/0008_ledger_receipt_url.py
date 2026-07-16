"""Add receipt URLs to credit ledger purchases.

Revision ID: 0008_ledger_receipt_url
Revises: 0007_job_carried_langs
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008_ledger_receipt_url"
down_revision: str | None = "0007_job_carried_langs"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("credit_ledger", sa.Column("receipt_url", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("credit_ledger", "receipt_url")
