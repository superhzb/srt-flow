"""Public API surface for ``pkg_job_orch``.

Everything app/tests import lives here. Internal modules are private —
imports must target ``pkg_job_orch.api`` only (AGENTS.md).
"""

from __future__ import annotations

__all__ = [
    # config
    "JobOrchSettings",
    "load_settings",
    # db + engine
    "DEFAULT_DATABASE_URL",
    "get_engine",
    "init_schema",
    "reset_engine",
    "run_migrations",
    "session_scope",
    # models
    "Job",
    "CreditLedgerEntry",
    "FunnelEvent",
    "BalanceSnapshot",
    "balance_snapshot",
    "debit_job_once",
    "source_minutes",
    "ProcessedEvent",
    "User",
    "dropped_from_json",
    "dropped_to_json",
    "tgt_langs_from_csv",
    "tgt_langs_to_csv",
    # orchestration
    "DEV_USER_ID",
    "DEFAULT_DEV_USER_EMAIL",
    "EnqueueError",
    "EnqueueResult",
    "JobContext",
    "Notifier",
    "NullNotifier",
    "WorkerClientFn",
    "default_worker_client",
    "enqueue",
    "enqueue_pending",
    "list_pending",
    "recover_jobs",
    "seed_dev_user",
    "worker_loop",
    # worker client
    "StreamOutcome",
    "WorkerStreamError",
    "build_segments",
    "stream_translate",
    # worker registry
    "DEFAULT_WORKERS",
    "WorkerInfo",
    "WorkerResolutionError",
    "WorkerStatus",
    "fetch_languages",
    "probe_workers",
    "worker_base_url",
    "workers_env",
    # router
    "router",
    "require_job_user",
]

from .config import JobOrchSettings, load_settings
from .credits import BalanceSnapshot, balance_snapshot, debit_job_once, source_minutes
from .db import (
    DEFAULT_DATABASE_URL,
    get_engine,
    init_schema,
    reset_engine,
    run_migrations,
    session_scope,
)
from .models import (
    CreditLedgerEntry,
    FunnelEvent,
    Job,
    ProcessedEvent,
    User,
    dropped_from_json,
    dropped_to_json,
    tgt_langs_from_csv,
    tgt_langs_to_csv,
)
from .orchestration import (
    DEFAULT_DEV_USER_EMAIL,
    DEV_USER_ID,
    EnqueueError,
    EnqueueResult,
    JobContext,
    Notifier,
    NullNotifier,
    WorkerClientFn,
    default_worker_client,
    enqueue,
    enqueue_pending,
    list_pending,
    recover_jobs,
    seed_dev_user,
    worker_loop,
)
from .routes import require_job_user, router
from .worker_client import (
    StreamOutcome,
    WorkerStreamError,
    build_segments,
    stream_translate,
)
from .workers import (
    DEFAULT_WORKERS,
    WorkerInfo,
    WorkerResolutionError,
    WorkerStatus,
    fetch_languages,
    probe_workers,
    worker_base_url,
    workers_env,
)
