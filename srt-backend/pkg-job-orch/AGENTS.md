# AGENTS

Rules for AI agents working inside this package:

- Public API lives in `api.py`; the package root is not a public API surface.
- Interfaces are defined as `Protocol` types.
- Tests import only from `package.api`, never internal modules.
- Imports must have no side effects; load config/env at explicit runtime boundaries.
- Never write to stdout or stderr.
- Logging uses `logging.getLogger(__name__)` only, with no handlers configured in library code.
- Packages may own config/env loading and credential discovery when needed for internal use.
- Never hard-code secrets, commit credentials, or log secret values; keep env/config behavior explicit and testable.
- Keep `ruff`, `pyright --strict`, and `pytest` passing at all times.

## Analytics events

- One generic `event` table (see `models.Event`, `events.py`). It replaced the
  old `funnel_events` table — do not reintroduce per-funnel tables.
- Every event type MUST have an entry in `events.EVENT_CATALOG` before it is
  emitted. The catalog is the contract: it fixes the source side
  (`server`/`client`) and the props whitelist. Unknown types or unlisted prop
  keys are rejected on write (`record_event` raises `ValueError`).
- Emit via `record_event(session, ...)` inside the caller's own transaction —
  it uses a nested savepoint, so a duplicate `dedup_key` rolls back only the
  event insert, never the surrounding unit of work. Pass a `dedup_key` for
  facts that must land at most once (job lifecycle, purchases); omit it for
  intents that may legitimately repeat (checkout, screen views).
- `created_at` is always server-set. Never trust a client-supplied timestamp.
- No PII in `props`. anon→user identity is joined at query time via `anon_id`;
  rows are never rewritten to backfill identity.
- Retention: `anonymize_old_events` nulls `user_id`/`anon_id` (and any
  identifying props) past the horizon (default 365 days) while preserving the
  fact. Run it on a schedule; it is idempotent.
