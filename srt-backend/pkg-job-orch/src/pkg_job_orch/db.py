"""Database engine + migrations runner.

Owns the single SQLAlchemy ``Engine``. Config (``DATABASE_URL``) is read
**at a runtime boundary** (the app lifespan calls :func:`run_migrations`
then :func:`get_engine`), never at import. The engine cache is
module-level so the whole process shares one connection pool; tests use
:func:`reset_engine` to swap in a fresh temp DB.

SQLite only for slice 3 — schema is portable to Postgres later via the
same Alembic migrations.
"""

from __future__ import annotations

import os
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy.engine import Engine
from sqlmodel import Session, create_engine, select

from .models import Job, User

__all__ = [
    "DEFAULT_DATABASE_URL",
    "get_engine",
    "reset_engine",
    "session_scope",
    "run_migrations",
    "init_schema",  # test-only shortcut
]

DEFAULT_DATABASE_URL = "sqlite:///./.data/dev/db.sqlite"

_engine: Engine | None = None


def _resolve_url(database_url: str | None) -> str:
    return database_url or os.environ.get("DATABASE_URL", DEFAULT_DATABASE_URL)


def get_engine(database_url: str | None = None) -> Engine:
    """Return the cached engine, building it on first call.

    Subsequent calls reuse the cached engine regardless of ``database_url``
    — pass ``database_url`` only on the first call (the lifespan does this).
    Tests call :func:`reset_engine` between cases to swap engines.
    """
    global _engine
    if _engine is None:
        url = _resolve_url(database_url)
        # check_same_thread=False: the worker_loop (asyncio) and the request
        # threadpool both touch the engine. SQLite serialises writes itself.
        _engine = create_engine(url, connect_args={"check_same_thread": False})
    return _engine


def reset_engine() -> None:
    """Drop the cached engine. Test-only — never call in app code."""
    global _engine
    if _engine is not None:
        _engine.dispose()
    _engine = None


@contextmanager
def session_scope(database_url: str | None = None) -> Generator[Session, None, None]:
    """Session context manager that commits on success, rolls back on error.

    ``expire_on_commit=False`` so callers can read attributes after the
    ``with`` block closes (common in routes that build response dicts
    from the just-committed row).
    """
    engine = get_engine(database_url)
    session = Session(engine, expire_on_commit=False)
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def _migrations_dir() -> Path:
    # migrations/ ships inside the installed package (see hatch wheel config).
    return Path(__file__).resolve().parent / "migrations"


def run_migrations(database_url: str | None = None) -> None:
    """Run ``alembic upgrade head`` against ``database_url``.

    Programmatic invocation — no alembic.ini needed. The migrations
    directory ships inside the package so this works regardless of cwd.
    """
    from alembic import command
    from alembic.config import Config

    url = _resolve_url(database_url)
    cfg = Config()
    cfg.set_main_option("script_location", str(_migrations_dir()))
    cfg.set_main_option("sqlalchemy.url", url)
    command.upgrade(cfg, "head")


def init_schema(database_url: str | None = None) -> None:
    """Create all tables directly from SQLModel metadata (test-only).

    Tests use this against an in-memory SQLite for speed; production
    paths go through :func:`run_migrations` (Alembic).
    """
    from sqlmodel import SQLModel

    engine = get_engine(database_url)
    SQLModel.metadata.create_all(engine)


def count_jobs_by_status(session: Session, status: str) -> int:
    """Helper for tests / diagnostics."""
    stmt = select(Job).where(Job.status == status)
    return len(session.exec(stmt).all())


def get_user_by_email(session: Session, email: str) -> User | None:
    stmt = select(User).where(User.email == email)
    return session.exec(stmt).first()
