# Analytics / Event Tracking — Implementation Plan

Status: **BUILT** (rev 3, 2026-07-17) — P1–P4 landed.

Prototype deviations from the plan (no backward compat, per instruction):
- **One migration, not A/B/C.** `0009_event_table` drops `funnel_events`
  outright and creates `event`. No parallel writes, no backfill, no bake — old
  data discarded. `FunnelEvent` model removed entirely.
- **Signup/login emit in `AppStore.upsert`**, not `google.py`. `upsert` already
  holds the session and knows created-vs-existing, so no created-flag is
  threaded up. `user_logged_in` uses no `dedup_key` (each login is distinct).
- **`_mark_done` is `orchestration._land_results`** (the plan's line number was
  stale); `job_completed` emits there.
- Retention is a callable (`anonymize_old_events`), not yet wired to a
  scheduler — no scheduler infra exists in the app.

Tests: `srt-backend/tests/test_events.py`. Full backend suite + frontend
`tsc`/`eslint`/`vitest` green.

Locked decisions:
1. New generic `event` table (not widen `funnel_events`).
2. Plan only for now — no code yet.
3. **Retention**: anonymize after horizon (default 12 months) — see Privacy.
4. **Consent**: no gate — functional first-party analytics.
5. **User FK**: keep FK on `user.id`; no deletion planned; if erasure added later use `ON DELETE SET NULL`.

## Context — what already exists

- **`FunnelEvent` table** (`funnel_events`) — `pkg-job-orch/.../models.py:138`.
  Row: `id, user_id, event_type, pack, created_at`. Only `checkout_started` emitted today.
- **Emitter pattern** — `AppStore.record_checkout_started` (`src/srt_backend/app_store.py:398`).
- **Webhook idempotency already built** — `AppStore.apply_paid_webhook_once`, `ProcessedEvent`,
  `idempotency_key` keyed on Stripe `event_id` (`app_store.py:148+`). Purchase events ride this.
- **Job terminal transitions are single points** — `_mark_done` (`orchestration.py:514`,
  sets `status="done"` + `finished_at`) and `_mark_failed` (`:530`). Emit there.
- **No user-deletion code exists** (only cookie clears). FK to `user.id` safe today.
- **No third-party analytics** anywhere. SQLite now, Postgres-portable via Alembic.
- **Admin**: SQLAdmin, read-only ModelViews, OAuth + `is_admin`, mounted `/admin` (`admin.py`).
- **Frontend**: React SPA, fetch chokepoint `apiFetch` (`lib.ts:129`), anon-id via `clientStorage.ts`.

## Principles

1. **Own event data first** — first-party table beats a SaaS pixel at this scale.
2. **Server-side for truth, client-side for UI.** Revenue/lifecycle = server; clicks/views = client.
3. **One generic `event` table.**
4. **One ingestion path each side** — `AppStore.record_event` (server), `POST /api/events` (client).
5. **Append-only for facts** — event rows are never edited to change what happened. Identity
   anonymization (nulling `user_id`/`anon_id`/PII props) is a separate, allowed operation.
6. **Product analytics ≠ ops metrics** — latency/error/uptime handled elsewhere.

## Schema

```
event(
  id            str  PK
  event_type    str  indexed          # canonical name, see catalog
  user_id       str  nullable, indexed, FK user.id      # ON DELETE SET NULL if erasure added
  anon_id       str  nullable          # pre-login continuity, from clientStorage
  source        str  'server' | 'client'
  session_id    str  nullable          # client UUID, 30-min inactivity rotation
  dedup_key     str  nullable, UNIQUE  # enforces at-most-once (see catalog)
  props         JSON                    # whitelisted keys only
  created_at    datetime indexed        # SERVER-set, never client-supplied
)
```

Indexes: `(event_type, created_at)`, `user_id`. `dedup_key` UNIQUE →
insert-or-ignore makes emission idempotent for keyed events.

## Event catalog (contract)

Every event type MUST have a row here before it is emitted. Past-tense outcome names.

| Event               | Exact trigger                                   | Source | Required props            | Dedup key                 |
|---------------------|-------------------------------------------------|--------|---------------------------|---------------------------|
| `user_signed_up`    | First successful user creation (upsert = new)   | server | `provider`                | `user_id`                 |
| `user_logged_in`    | Successful auth of existing user                | server | `provider`                | `login_id` (per session)  |
| `job_created`       | Job row committed (`routes.py:68`)              | server | `job_id`, `src_lang`, `tgt_langs` | `job_id`          |
| `job_completed`     | First transition to `done` (`_mark_done`)       | server | `job_id`, `source_minutes`| `job_id` + `:completed`   |
| `job_failed`        | First transition to `failed` (`_mark_failed`)   | server | `job_id`, `error_kind`    | `job_id` + `:failed`      |
| `checkout_started`  | Stripe checkout session created                 | server | `pack`                    | (none — intent, may repeat)|
| `purchase_completed`| Verified paid webhook grants credits            | server | `pack`, `ledger_entry_id` | stripe `event_id`         |
| `credits_debited`   | Each `CreditLedgerEntry` debit write            | server | `reason`, `amount`, `balance_after`, `job_id?`, `ledger_entry_id` | `ledger_entry_id` |
| `screen_viewed`     | SPA tab/screen shown                            | client | `screen`                  | (none)                    |
| `demo_started`      | Demo flow begins                                | client | —                         | (none)                    |
| `cta_clicked`       | Named CTA pressed                               | client | `cta`                     | (none)                    |

Rules: no card/Stripe-token/PII in `props`; `props` keys must be on the whitelist;
unknown `event_type` from client is rejected. Duplicate `dedup_key` = silently ignored.

## Migration sequence (no lost/dup events)

1. Migration A: create `event` table + indexes + UNIQUE(`dedup_key`). Deploy. (Additive, safe.)
2. Code: `record_event` + all server emitters go live writing to `event`.
   `record_checkout_started` rerouted to `record_event('checkout_started', ...)`.
   `funnel_events` still written **in parallel** by nothing new — legacy stays read-only.
3. Migration B (data): copy existing `funnel_events` rows → `event`
   (`event_type` preserved, `pack`→`props.pack`, deterministic id so re-run is idempotent).
4. Bake period — confirm `event` receiving all types, dashboards read `event` only.
5. Migration C: drop `funnel_events` once confirmed unused.

Never drop before copy+bake. Steps 1→5 are separate deploys.

## Privacy / retention

- **Retention**: nightly/weekly job anonymizes rows older than **12 months** — null
  `user_id`, `anon_id`, and any identifying `props`; keep `event_type`, `created_at`,
  aggregate props. Row facts unchanged (append-only honored).
- **Consent**: none — first-party functional analytics, no advertising, no cookie banner.
  Revisit if EU/UK targeting or ad-network events added.
- **Erasure/FK**: keep FK; no user deletion today. If added, `ON DELETE SET NULL`
  (retention already anonymizes, so historical analytics survive).
- **Props whitelist** enforced server-side on every write, both sources.

## Client tracking (explicit only)

- Do **NOT** auto-track every `apiFetch` request — noisy and low-value.
- One `track(event_type, props)` helper → buffers → `POST /api/events`.
- `/api/events` itself is excluded from any instrumentation (no recursion).
- `session_id`: UUID minted in `clientStorage`, rotates after 30 min inactivity.
- `anon_id`: stable per-browser id; sent on events before + after login.
  Join anon→user at **query time** (`anon_id` → first `user_id` seen). Never rewrite rows.

## POST /api/events limits

- `created_at` set by server, client value ignored.
- Batch ≤ 20 events; body ≤ 16 KB; reject over-limit.
- `event_type` must be in client-allowed catalog subset; unknown → 400.
- Per-session rate limit (e.g. 60/min). Auth optional (anon allowed).

## Admin

- **Now**: `EventAdmin(ModelView)` in `admin.py` — raw browse, filter by type/user/date.
- **Analytics**: SQLAdmin **custom page** at `/admin/analytics` rendering plain HTML tables
  from aggregate SQL (DAU, `user_signed_up`→`purchase_completed` conversion, jobs/day,
  funnel drop-off). No new dep, no hand-built charts.
- **Later**: Metabase/Grafana on the DB — defer until Postgres.

## Plan (phased — incrementally deployable; P2 needs P1, P3 needs P1)

### Phase 1 — event backbone (server)
1. Migration A: create `event` table (see schema).
2. `Event` SQLModel in `models.py`.
3. `AppStore.record_event(event_type, *, user_id=None, anon_id=None, source='server', session_id=None, dedup_key=None, props=None)`;
   reroute `record_checkout_started` through it.
4. Emit server events per catalog:
   - `user_signed_up` / `user_logged_in` → `pkg-auth/.../google.py:78` (upsert must return created-flag)
   - `job_created` → `pkg-job-orch/.../routes.py:68`
   - `job_completed` / `job_failed` → `orchestration.py` `_mark_done` / `_mark_failed` (guard first transition)
   - `purchase_completed` / `credits_debited` → `app_store.py` webhook + ledger writes
5. Migration B: backfill `funnel_events` → `event`.

### Phase 2 — admin visibility (needs P1)
6. `EventAdmin` ModelView.
7. `/admin/analytics` custom page + aggregate queries.

### Phase 3 — client events (needs P1)
8. `POST /api/events` (limits above).
9. `track()` helper + `session_id`/`anon_id` in `clientStorage`; wire explicit calls in
   `App.tsx` / `BillingScreen.tsx`. Unify direct-`fetch` calls in `api.ts` first.

### Phase 4 — hardening
10. Props whitelist enforcement + anonymization retention job (12mo). Document in AGENTS.md.
11. Migration C: drop `funnel_events` after bake.

## Key file touch points

| Concern            | Path |
|--------------------|------|
| Models             | `srt-backend/pkg-job-orch/src/pkg_job_orch/models.py` |
| Migrations         | `srt-backend/pkg-job-orch/src/pkg_job_orch/migrations/versions/` |
| Server emitter     | `srt-backend/src/srt_backend/app_store.py` |
| Signup/login       | `srt-backend/pkg-auth/src/pkg_auth/google.py:78` |
| Job created        | `srt-backend/pkg-job-orch/src/pkg_job_orch/routes.py:68` |
| Job terminal       | `srt-backend/pkg-job-orch/src/pkg_job_orch/orchestration.py:514,530` |
| Purchase/debit     | `srt-backend/src/srt_backend/app_store.py:148+` (webhook), `credits.py` |
| Admin              | `srt-backend/src/srt_backend/admin.py` |
| Client fetch hook  | `srt-frontend/src/lib.ts:129` |
| Client handlers    | `srt-frontend/src/App.tsx`, `BillingScreen.tsx` |
| Anon/session id    | `srt-frontend/src/clientStorage.ts` |
