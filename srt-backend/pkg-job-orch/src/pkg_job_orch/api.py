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
    "Event",
    "BalanceSnapshot",
    "balance_snapshot",
    "billed_minutes",
    "debit_job_once",
    "source_minutes",
    "ProcessedEvent",
    "User",
    "dropped_from_json",
    "dropped_to_json",
    "tgt_langs_from_csv",
    "tgt_langs_to_csv",
    # events
    "CLIENT_ALLOWED_EVENTS",
    "DEFAULT_RETENTION_DAYS",
    "EVENT_CATALOG",
    "EventSpec",
    "anonymize_old_events",
    "record_event",
    "validate_props",
    # retention + erasure
    "DEFAULT_JOB_RETENTION_DAYS",
    "DEFAULT_RETENTION_INTERVAL_SECONDS",
    "ErasureResult",
    "erase_user",
    "purge_old_jobs",
    "retention_loop",
    "run_retention_pass",
    # orchestration
    "DEV_USER_ID",
    "DEFAULT_DEV_USER_EMAIL",
    "EnqueueError",
    "EnqueueResult",
    "JobContext",
    "Notifier",
    "NullNotifier",
    "StreamOutcome",
    "WorkerClientFn",
    "WorkerStreamError",
    "build_segments",
    "default_worker_client",
    "enqueue",
    "enqueue_pending",
    "list_pending",
    "recover_jobs",
    "seed_dev_user",
    "worker_loop",
    # worker registry
    "WorkerInfo",
    "WorkerResolutionError",
    "WorkerStatus",
    "fetch_languages",
    "probe_workers",
    "worker_backend_config",
    "workers_env",
    # router
    "router",
    "require_job_user",
]

from .config import JobOrchSettings, load_settings
from .credits import (
    BalanceSnapshot,
    balance_snapshot,
    billed_minutes,
    debit_job_once,
    source_minutes,
)
from .db import (
    DEFAULT_DATABASE_URL,
    get_engine,
    init_schema,
    reset_engine,
    run_migrations,
    session_scope,
)
from .erasure import ErasureResult, erase_user
from .events import (
    CLIENT_ALLOWED_EVENTS,
    DEFAULT_RETENTION_DAYS,
    EVENT_CATALOG,
    EventSpec,
    anonymize_old_events,
    record_event,
    validate_props,
)
from .models import (
    CreditLedgerEntry,
    Event,
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
    StreamOutcome,
    WorkerClientFn,
    WorkerStreamError,
    build_segments,
    default_worker_client,
    enqueue,
    enqueue_pending,
    list_pending,
    recover_jobs,
    seed_dev_user,
    worker_loop,
)
from .retention import (
    DEFAULT_JOB_RETENTION_DAYS,
    DEFAULT_RETENTION_INTERVAL_SECONDS,
    purge_old_jobs,
    retention_loop,
    run_retention_pass,
)
from .routes import require_job_user, router
from .workers import (
    WorkerInfo,
    WorkerResolutionError,
    WorkerStatus,
    fetch_languages,
    probe_workers,
    worker_backend_config,
    workers_env,
)
