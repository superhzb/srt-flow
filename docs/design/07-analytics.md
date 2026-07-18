# 07 — Analytics / Events

## Overview

Product analytics is a single first-party append-only table, `event`, with two
ingestion paths that share one function: server emitters call
`record_event` inside their own transaction, and the browser POSTs explicit
events to `/api/events` which routes through the same function. Every event
type is declared in one catalog (`events.EVENT_CATALOG`) that enforces a props
whitelist on every write regardless of source; there is no third-party
analytics SaaS. Revenue and lifecycle facts are emitted server-side (truth);
screen views and clicks are emitted client-side (UI).

## Data model

`Event` — `pkg-job-orch/.../models.py:Event`, table `event`:

| Column       | Notes |
|--------------|-------|
| `id`         | PK, `uuid4().hex` |
| `event_type` | indexed; canonical name, must exist in the catalog |
| `user_id`    | nullable, indexed, FK `user.id` |
| `anon_id`    | nullable; per-browser id, joined anon→user at query time (rows never rewritten) |
| `source`     | `"server"` \| `"client"`, defaults `"server"` |
| `session_id` | nullable; client session UUID |
| `dedup_key`  | nullable, **UNIQUE**; enforces at-most-once for keyed events |
| `props`      | JSON, `NOT NULL`, whitelisted keys only |
| `created_at` | indexed; **always server-set**, a client-supplied value is ignored |

Composite index `ix_event_type_created_at` on `(event_type, created_at)`, plus
single-column indexes on `event_type`, `user_id`, `created_at`.

Created by migration `0009_event_table`
(`.../migrations/versions/0009_event_table.py`): it drops the old
`funnel_events` table and its indexes outright and creates `event` with
`UniqueConstraint("dedup_key")`. No data is migrated — the `FunnelEvent` model
is gone.

## Ingestion (`pkg-job-orch/.../events.py`)

`events.py:record_event(session, event_type, *, user_id, anon_id, source,
session_id, dedup_key, props)` is the one write path. It validates the type and
props against the catalog (`events.py:validate_props`), and for a keyed event
first checks for an existing `dedup_key`, returning `None` if found. The insert
runs in a nested savepoint (`session.begin_nested`) so a duplicate — including a
concurrent one that trips the UNIQUE constraint via `IntegrityError` — rolls
back only itself, never the caller's surrounding transaction. Returns the new
row or `None` when nothing was written.

`events.py:validate_props` raises `ValueError` for an unknown `event_type` or
any prop key not on that type's `EventSpec.allowed_props` frozenset.

`AppStore.record_event` (`srt_backend/app_store.py:record_event`) is a thin
async wrapper that opens its own session and calls the module function — the
"standalone" path used when the caller isn't already in a transaction.
`AppStore.record_checkout_started` (`app_store.py:record_checkout_started`)
calls it with `event_type="checkout_started"`, `props={"pack": pack}`, and no
dedup key (intent, may repeat).

## Event catalog

The catalog (`events.py:EVENT_CATALOG`) is the source of truth; a type absent
from it cannot be written. `CLIENT_ALLOWED_EVENTS` is derived as the subset with
`source == "client"`.

| Event | Source | Emitted at (`path:symbol`) | Props | Dedup key |
|-------|--------|----------------------------|-------|-----------|
| `user_signed_up` | server | `app_store.py:upsert` (when `created`) | `provider` (`"google"`) | `user_id` |
| `user_logged_in` | server | `app_store.py:upsert` (existing user) | `provider` (`"google"`) | none (each login distinct) |
| `job_created` | server | `pkg-job-orch/.../routes.py` job-create handler | `job_id`, `src_lang`, `tgt_langs` | `job_id` |
| `job_completed` | server | `orchestration.py:_land_results` | `job_id`, `source_minutes` | `"{job_id}:completed"` |
| `job_failed` | server | `orchestration.py:_mark_failed` | `job_id`, `error_kind` | `"{job_id}:failed"` |
| `job_retried` | server | `pkg-job-orch/.../routes.py` retry handler | `job_id`, `attempt` | `"{job_id}:retried:{attempts}"` |
| `checkout_started` | server | `app_store.py:record_checkout_started` | `pack` | none (intent, may repeat) |
| `purchase_completed` | server | `app_store.py:apply_purchase_once` | `pack`, `ledger_entry_id` | Stripe `event_id` |
| `credits_debited` | server | `pkg-job-orch/.../credits.py:debit_job_once` | `reason`, `amount`, `balance_after`, `job_id`, `ledger_entry_id` | `ledger_entry_id` |
| `screen_viewed` | client | `App.tsx` screen-change effect | `screen` | none |
| `demo_started` | client | `App.tsx` (start-demo handler) | none | none |
| `cta_clicked` | client | `BillingScreen.tsx` buy handler | `cta` (`"buy_{pack}"`) | none |

Notes on the keyed emitters:
- `user_signed_up`/`user_logged_in` both fire from `AppStore.upsert`, which
  holds the session and knows created-vs-existing; sign-up is keyed on `user_id`
  (once ever), login carries no dedup key.
- `purchase_completed` reuses the Stripe `event_id`, the same idempotency the
  `ProcessedEvent` row enforces, so the fact lands at most once.
- `credits_debited` and `job_created`/`completed`/`failed`/`retried` all emit
  inside the same transaction that writes the underlying row, keyed so a retry
  of the surrounding operation does not duplicate the event.

## Client pipeline

`analytics.ts:track(event_type, props)` buffers events and flushes as a batch
(≤20) to `/api/events` after a 2s delay, or immediately when the buffer fills;
`analytics.ts:flush` posts with `fetch(..., keepalive)`, and a `pagehide`
listener flushes any remainder via `navigator.sendBeacon`. Failures are
swallowed — analytics never breaks a user flow — and `/api/events` is never
itself tracked. The envelope carries `session_id` and `anon_id` from
`clientStorage.ts`. `ClientEventType` is the TypeScript union
`"screen_viewed" | "demo_started" | "cta_clicked"`.

Identity ids come from `clientStorage.ts`: `getAnonId` mints a stable
per-browser UUID in `localStorage`; `getSessionId` mints a session UUID that
rotates after 30 minutes of inactivity (`SESSION_TTL_MS`). Both are opaque
UUIDs, no PII.

`POST /api/events` (`srt_backend/routes_events.py:ingest_events`, router prefix
`/events`) accepts `202`. Guards, in order: body ≤ 16 KB (`413`); JSON parses to
an `EventsBatch` of 1–20 `ClientEvent` (`400`); per-key rate limit of 60/min in
a sliding window keyed by `session_id`, else `anon_id`, else client IP (`429`);
every `event_type` must be in `CLIENT_ALLOWED_EVENTS`, else `400`. Auth is
optional — `resolve_user` attaches a `user_id` if present but anonymous callers
are accepted so pre-login views still land carrying only `anon_id`. Each event
is written via `record_event` with `source="client"`; a props whitelist
violation (`ValueError`) rejects the whole batch with `400`. `created_at` is
server-set; client timestamps are never accepted.

## Admin

Mounted under `/admin` (see doc 02 for admin-console basics: SQLAdmin,
OAuth + `is_admin`). Both views are registered in
`admin.py:register_admin`.

- `admin.py:EventAdmin` — read-only `ModelView` over `Event`
  (`can_create/edit/delete/export/import = False`), default-sorted by
  `created_at` desc, list columns `created_at, event_type, source, user_id,
  anon_id, props`, searchable on `event_type, user_id, anon_id`.
- `admin.py:AnalyticsView` — a `BaseView` exposing `GET /admin/analytics` that
  runs aggregate SQL against the `event` table and renders plain Tabler-styled
  HTML tables (via `admin.py:_render_table`), no JS charts: sign-up →
  purchase conversion (`user_signed_up` vs `purchase_completed` distinct users,
  with a percentage), events by type, daily active users (last 14 days, distinct
  non-null `user_id`), jobs created per day (last 14 days), and a job funnel
  (`job_created` / `job_completed` / `job_failed` counts).

## Retention / privacy

`events.py:anonymize_old_events(session, *, retention_days=DEFAULT_RETENTION_DAYS,
now=None)` nulls `user_id` and `anon_id` on rows older than the horizon
(`DEFAULT_RETENTION_DAYS = 365`) and strips any keys in
`events.py:IDENTIFYING_PROPS`, while leaving `event_type`, `created_at`, and
aggregate props intact — the row's fact is preserved (append-only), only
who-did-it is forgotten. Returns the count anonymized. `IDENTIFYING_PROPS` is
currently an empty frozenset (the catalog carries no PII props); the machinery
exists so a future PII-bearing prop is anonymized without further code changes.
There is no consent gate — first-party functional analytics, no advertising.

## Known gaps

- `anonymize_old_events` is a callable only; no scheduler wires it up (no
  scheduler infra exists in the app), so retention is not yet enforced
  automatically.
- Migration `0009_event_table` is a prototype cutover: it drops `funnel_events`
  and creates `event` in one step with no parallel-write, backfill, or bake
  period, so all pre-migration funnel data was discarded.
