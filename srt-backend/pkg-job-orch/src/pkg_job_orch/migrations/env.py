"""Alembic migrations environment.

Run programmatically by ``pkg_job_orch.db.run_migrations`` (no alembic.ini).
Uses ``SQLModel.metadata`` as the autogenerate target so future revisions
can diff against the live models.
"""

from __future__ import annotations

import logging

from alembic import context

# Make sure all table-bearing models are imported so SQLModel.metadata
# is fully populated before autogenerate runs.
from pkg_job_orch import models as _models
from pkg_job_orch.config import load_settings
from sqlalchemy import engine_from_config, pool
from sqlmodel import SQLModel

_ = _models

config = context.config

# Inject the runtime DATABASE_URL if Alembic was invoked programmatically
# (config.set_main_option("sqlalchemy.url", …)). Fall back to env via settings.
if not config.get_main_option("sqlalchemy.url"):
    config.set_main_option("sqlalchemy.url", load_settings().database_url)

_log = logging.getLogger("alembic.env.job_orch")


target_metadata = SQLModel.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=str(url) if url else None,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,  # SQLite-friendly ALTER
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=True,  # SQLite-friendly ALTER
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
