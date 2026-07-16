# Billing & Account Page — Design + Implementation Plan

## Context

`note.md` asks the billing page to gain **account info**, **billing history**, and other
accounting features for a paid SaaS, and to reuse the History panel's gradient credit
progress-bar style. Today `srt-frontend/src/BillingScreen.tsx` only shows a minutes
balance + two purchase packs. All the data for a real accounting view already exists in
the backend — the `CreditLedgerEntry` append-only ledger records purchases, refunds,
disputes, and per-job usage debits — but **no endpoint exposes it**. This plan surfaces
that ledger and redesigns the page into a proper Billing & Account view.

Decisions confirmed with user:
- **Model:** keep pay-as-you-go credit packs (no subscriptions).
- **History:** money/credit transactions only — purchases + refunds + disputes + paid-credit
  usage debits, filterable. Free-tier per-translation usage (0 credit impact) is excluded;
  it lives in the usage bar + Jobs screen.
- **Extras:** usage progress bar (gradient, from `note.md`) + per-purchase Stripe receipt links.
- **Scope:** full — new backend endpoint + frontend redesign, wired to real data.

## Page design (top → bottom, inside `BillingScreen`)

1. **Account overview card** — `TierBadge`, email, "Member since {date}", short account id.
   Uses `Card` from `ui.tsx`.
2. **Credits & usage card** — big available-minutes number (`gradient-text`), a **gradient
   usage bar** (free_used / free_limit), and a breakdown row: free-this-month, purchased
   balance. This is the `note.md` progress bar.
3. **Buy minutes** — existing pack grid (small/large), unchanged.
4. **Billing history** — **money/credit transactions only** (decided): purchases, refunds,
   disputes, and paid-credit usage debits. Table: date · type · description · minutes (±) ·
   amount · receipt. Type filter (All / Purchases / Usage / Adjustments), **server-side** —
   changing it resets pagination and refetches (see backend `category` param). Newest first.
   - **Free-tier `job_debit` rows are excluded.** Every successful translation writes a
     `job_debit` ledger row (`debit_job_once`, credits.py:77), but free-tier jobs consume no
     purchased credit (`minutes_delta=0`) — listing them would flood billing history with rows
     that have zero money/credit effect. Per-translation detail belongs on the Jobs screen; the
     Credits & usage card's bar already summarises free-tier consumption. Only `job_debit` rows
     that actually drew down purchased credit (`minutes_delta<0`) appear here, under "Usage".

All sections use existing tokens (`bg-surface`, `text-ink-muted`, `border-border`,
`bg-accent`) so light/dark work automatically.

## Backend changes

**1. Expose the ledger** — `srt-backend/pkg-billing/src/pkg_billing/api.py`
- Add `GET /billing/history?limit=&before=&category=` (auth via `get_current_user`), returns
  `{ entries: [...], has_more: bool, next_cursor: str | null }`.
  - **Query params (bounded):** `limit = Query(50, ge=1, le=100)`. Validation lives on the route
    and **rejects** out-of-range values with FastAPI's automatic `422` (no silent
    clamping/coercion).
  - **Keyset cursor (decided) — not offset.** Offset pagination duplicates/skips rows when a new
    ledger row is inserted between "Load more" requests (new rows sort to the top and shift every
    offset). Page by a `(created_at, id)` cursor instead: `before` is an opaque cursor string
    encoding the last returned row's `(created_at, id)` (e.g. base64 `"<iso>|<id>"`); absent on the
    first page. The query returns rows strictly **after** the cursor in `(created_at desc, id desc)`
    order. Robust against concurrent inserts.
  - **Base filter — exclude zero-impact usage (decided):** every query (all categories) excludes
    free-tier usage rows: `NOT (entry_type == "job_debit" AND minutes_delta == 0)`. History is
    money/credit only; per-job free usage is not a billing event. Apply this in `list_ledger`
    unconditionally.
  - **Server-side category filter (decided):** `category` in
    `all | purchases | usage | adjustments`, default `all`. Maps to `entry_type` (on top of the
    base filter): `purchases → {"purchase"}`, `usage → {"job_debit"}` (paid debits only, since the
    base filter already drops the `minutes_delta==0` ones),
    `adjustments → {"refund", "dispute", "dispute_reinstated"}`, `all → no entry_type filter`.
    Include `dispute_reinstated` (app_store.py:233) — omitting it hides reinstatements from the
    Adjustments filter. Validate via `Query("all")` + `Literal`/enum. The frontend **drops the
    cursor and refetches from the top** whenever the filter changes (not client-side over loaded
    pages), so an older matching row is never falsely absent.
  - **Continuation:** fetch `limit + 1` rows; `has_more = len(rows) > limit`; trim to `limit`;
    `next_cursor` = encoded `(created_at, id)` of the last returned row when `has_more`, else `null`.
- Add `list_ledger(user_id, limit, cursor=None, entry_types=None)` to the `BillingStore` Protocol
  in `pkg_billing/store.py` and implement in `AppStore`
  (`srt-backend/src/srt_backend/app_store.py`): `select(CreditLedgerEntry).where(user_id==...)`,
  `.where(~((entry_type == "job_debit") & (minutes_delta == 0)))` (base filter, always),
  `.where(entry_type.in_(entry_types))` when set, keyset predicate when `cursor` is set —
  `(created_at, id) < (cursor.created_at, cursor.id)` (row-value comparison, or the equivalent
  `created_at < c.created_at OR (created_at == c.created_at AND id < c.id)`) —
  `.order_by(CreditLedgerEntry.created_at.desc(), CreditLedgerEntry.id.desc()).limit(limit + 1)`.
  - **`id` tie-breaker is load-bearing:** `created_at` is not unique, so both the ORDER BY and the
    keyset predicate need the secondary `id` to give a total order and avoid dup/skip at equal
    timestamps.
- **New `BillingStore` Protocol methods** — the receipt-enrichment and confirm flows call methods
  that don't exist on the Protocol today; add all three and implement in `AppStore` **and** every
  test fake:
  - `list_ledger(user_id, limit, cursor=None, entry_types=None)` (above).
  - `set_receipt_url(session_id, url)` → `UPDATE credit_ledger SET receipt_url=? WHERE session_id=?`.
  - `has_purchase(user_id, session_id) -> bool` → exists a `purchase` row for that user + session
    (backs `GET /billing/confirm`).
- DTO per entry: `id, created_at, entry_type, minutes_delta, usage_minutes, balance_after,
  pack, amount_cents, currency, reason, receipt_url`.
  - **`usage_minutes` kept for description context.** With free-tier usage excluded, every shown
    row has `minutes_delta != 0`, so the minutes column no longer needs `usage_minutes`. But paid
    `job_debit` rows still carry `usage_minutes` (total minutes translated) which the row
    *description* can show — e.g. "Translation — 40 min, 10 charged to credit". Keep it in the DTO.
    (`CreditLedgerEntry` already carries the column — models.py:122.)
  - **Display rule (decided):** the "minutes (±)" column shows the **credit impact** =
    `minutes_delta` for **all** rows (purchase +, refund/dispute −, reinstatement +, paid usage −).
    Already signed in the DB. No `entry_type` branching for this column.
  - **`created_at` must be the Stripe event time, not DB insertion time.** Ordering/display use
    `created_at`, but today the store discards the real timestamps: `apply_purchase_once` never
    sets `created_at` (falls back to `_utcnow` default_factory, i.e. insertion time) and only
    keeps `paid_at` on `ProcessedEvent`; `apply_refund_once`/`apply_dispute_once` receive
    `created_at` and `del` it (app_store.py:183, 205). Fix: pass the Stripe timestamp through to
    the `CreditLedgerEntry.created_at` for purchase, refund, and dispute rows (parse the ISO
    `paid_at`/`created_at` the webhook already computes via `_paid_at`). Otherwise a refund
    inserted after a later purchase would sort out of chronological order.

**2. Receipt links** — new column + populate on webhook
- Add nullable `receipt_url: str | None` to `CreditLedgerEntry`
  (`srt-backend/pkg-job-orch/src/pkg_job_orch/models.py`) + Alembic migration
  `0008_ledger_receipt_url.py` with `down_revision = "0007_job_carried_langs"` (revision `0007`
  is already taken by `0007_job_carried_langs`; mirror the column-add style of
  `0006_credit_ledger.py`).
- **Persist first, enrich best-effort (decided):** `apply_purchase_once` credits minutes
  atomically from the trusted signed webhook payload alone — it does **not** call Stripe. After
  the purchase row is committed (i.e. `apply_purchase_once` returned `True`), `_handle_event`
  fetches the receipt best-effort inside `run_in_threadpool`, then writes it onto the row. A
  transient Stripe failure leaves `receipt_url` null while minutes stay credited; log + swallow
  (never re-raise into the webhook 200 path). Only purchase entries carry a receipt.
  - **Update key — no entry_id exists.** `apply_purchase_once` returns `bool` and mints the row
    id internally (`id=uuid.uuid4().hex`, app_store.py:122); there is no id to hand to a setter.
    Update by the **unique `session_id`** already in scope: `set_receipt_url(session_id, url)` →
    `UPDATE credit_ledger SET receipt_url=? WHERE session_id=?` (`session_id` is `unique`,
    models.py:125). (Alternative: have `apply_purchase_once` return the id; the `session_id` key
    is simpler and keeps the bool contract.)
  - **Two-step retrieve — a bare `latest_charge` string has no `receipt_url`.**
    `receipt_url` lives on the **Charge**, not the PaymentIntent. Steps:
    1. `pi = stripe.PaymentIntent.retrieve(payment_intent_id, api_key=config.stripe_secret,
       expand=["latest_charge"])`.
    2. Resolve `latest_charge`: if it is an expanded **object** (dict), read `receipt_url`
       directly; if it is a bare **charge-id string** (not expanded), call
       `stripe.Charge.retrieve(charge_id, api_key=config.stripe_secret)` and read `receipt_url`
       from it. Do not treat the string id as if it carried a URL.
  - **`api_key` required** on **every** Stripe call above — matches every other Stripe call in
    this module (`_create_checkout_session_sync` passes `api_key` per-call).
  - **No backfill (decided — prototype scope):** receipt links exist only for purchases made
    after this ships. Pre-existing rows keep `receipt_url=null` and render no link. No
    backfill script and no lazy-on-read enrichment.

**3. Member-since + account id** — `srt-backend/pkg-auth/src/pkg_auth/router.py`
- Add `created_at` (ISO) **and** `id` to the `GET /auth/me` response. `User` already has both
  (`id` primary key models.py:92, `created_at` models.py:97). `AccountCard` needs `id` for the
  "short account id" line and `created_at` for "Member since"; the current response returns only
  `email, tier, is_admin`.

## Frontend changes

**`srt-frontend/src/api.ts`**
- Extend `Me` with `id: string` and `created_at: string` (currently only `email, tier, is_admin`).
- Add `BillingTransaction` type (mirror the DTO incl. `usage_minutes` + `receipt_url`) and a
  `BillingHistoryPage` type `{ entries: BillingTransaction[]; has_more: boolean; next_cursor: string | null }`.
- Add `getBillingHistory(opts?: { limit?: number; before?: string; category?: BillingCategory })`
  (`BillingCategory = "all" | "purchases" | "usage" | "adjustments"`) →
  `apiFetch("/api/billing/history" + query)`, returning `BillingHistoryPage`. Encode `before`
  (cursor) and `category` into the query string alongside `limit` (omit `before` on first page,
  `category` when `"all"`/undefined).
- Add `getBillingConfirm(sessionId: string)` → `apiFetch("/api/billing/confirm?session_id=...")`,
  returning `{ applied: boolean }` (drives the post-checkout poll).

**`srt-frontend/src/lib.ts`** (shared helpers — none exist today)
- Add `formatCurrency(cents, currency)` via `Intl.NumberFormat`.
- Add/export `formatLedgerDate()` (reuse the relative-date logic currently local in
  `JobsScreen.tsx:339`).

**`srt-frontend/src/components.tsx`**
- Add reusable `QuotaBar({ used, limit })` using the History bar markup
  (`bg-surface-inset` track + `bg-gradient-to-r from-accent to-info` fill). Reused on the
  billing page now; also unblocks fixing the `MOCK_QUOTA` History bug later (`note.md` bug 1).

**`srt-frontend/src/BillingScreen.tsx`** (main work)
- Load `getMe()` + `getBillingBalance()` + `getBillingHistory()` on mount (extend existing
  `refresh()`).
- **Fix the post-checkout confirmation poll.** Today `usePoll(() => getBillingBalance(),
  () => true, ...)` (line 96) stops after the *first* successful balance read, so it can resolve
  before the webhook applies the purchase, and it never refreshes history. A pre-checkout balance
  baseline **cannot** work here: `handleCheckout` does a full-page `window.location.href` redirect
  to Stripe, so in-memory state is gone on return — a post-return baseline may already include the
  purchase, and a `0` baseline false-positives for any user with existing balance. Instead track
  the **specific checkout session**:
  - Backend: put Stripe's `{CHECKOUT_SESSION_ID}` placeholder in `success_url`. **`success_url`
    is built with a Python f-string** (`f"{app_base_url}/?checkout=success"`, api.py:119) — write
    the placeholder **doubled** so the f-string emits a literal brace and doesn't try to evaluate
    `CHECKOUT_SESSION_ID` as a name: `f"{app_base_url}/?checkout=success&session_id={{CHECKOUT_SESSION_ID}}"`
    → Stripe receives `...&session_id={CHECKOUT_SESSION_ID}` and substitutes the real id on redirect.
  - Add a dedicated `GET /billing/confirm?session_id=` that returns `{ applied: bool }`.
    **Must depend on `get_current_user` and query by both `user_id` and `session_id`** — a lookup
    on `session_id` alone (a globally-unique column) would leak another user's checkout status.
    `applied = await store.has_purchase(user.id, session_id)` (see Protocol method above).
  - Frontend: **`session_id` must be captured in `App`, not read from the URL in `BillingScreen`.**
    App's getMe effect rewrites `/?...` → `/app` on load (App.tsx:126) and the checkout effect
    stores only `success`/`cancel` and deletes only the `checkout` param (App.tsx:164-167), so by
    the time `BillingScreen` mounts the query string (and `session_id`) is gone. Extend App's
    checkout effect to also read `session_id`, store it in state next to `checkoutStatus`, delete
    **both** query params in the `replaceState`, and pass `session_id` as a `BillingScreen` prop.
    `BillingScreen` polls `getBillingConfirm(session_id)` with predicate `res => res.applied` (keep
    `maxMs: 20_000` / `stopOnError: false`), enabled only when the prop is set.
  - On completion, reload **both** balance and ledger (`getBillingHistory()`) so the new purchase
    row appears.
- Render the 4 sections above. Extract `AccountCard`, `UsageCard` (with `QuotaBar`), and
  `HistoryTable` as local components. `AccountCard` uses `me.id` (short id) + `me.created_at`
  ("Member since"). History rows follow the existing bordered-row pattern (`JobsScreen`
  `JobListItem`); the minutes column shows `minutes_delta` for every row (see Display rule); paid
  `job_debit` rows use `usage_minutes` in their description text. "View receipt" is an
  `<a target="_blank">` when `receipt_url` is set. Empty state when no transactions.
- **Pagination + filter:** initial page fetches with no cursor; render a "Load more" button when
  `has_more`, calling `getBillingHistory({ before: next_cursor, category })` and **appending**
  rows. The category filter is server-side — on change, drop the cursor and **replace** (not
  append) rows so results reflect all history, not just loaded pages.

**`srt-frontend/src/App.tsx`** — extend the existing checkout effect (App.tsx:161-173) to also
capture `session_id`: read `url.searchParams.get("session_id")`, store it in state, delete
**both** `checkout` and `session_id` params in the `replaceState`, and pass it to `BillingScreen`
as a prop. (Needed so `session_id` survives the getMe `→ /app` rewrite.) Optional: relabel the
`billing` tab to "Billing" (map at line ~472). Tab + login gating already exist; no routing change.

## Verification

- **Backend:** add tests in `srt-backend/tests/test_billing_route.py` for `GET /billing/history`
  — auth required; seeded ledger rows newest-first; **free-tier `job_debit` rows
  (`minutes_delta=0`) are excluded** while paid `job_debit` rows (`minutes_delta<0`) appear under
  `usage`; `receipt_url` present on purchases; cursor pagination (`has_more`/`next_cursor` correct
  across two pages; out-of-range `limit` rejected with **422**).
  - Webhook receipt enrichment tests: purchase is credited even when `PaymentIntent.retrieve`
    raises (receipt_url stays null, minutes credited); `latest_charge` as an **expanded object**
    resolves `receipt_url` directly; `latest_charge` as a **bare string id** triggers
    `Charge.retrieve` (assert it's called) and resolves `receipt_url`; assert every Stripe call
    passes `api_key=config.stripe_secret`; `set_receipt_url` targets the row by `session_id`.
  - Timestamp test: `created_at` on purchase/refund/dispute rows equals the Stripe event time
    (not insertion time); rows sort chronologically when inserted out of order.
  - Confirm-endpoint test: `GET /billing/confirm?session_id=` returns `applied:false` before the
    purchase row exists and `applied:true` after `apply_purchase_once`; **a different user's**
    request for the same `session_id` returns `applied:false` (user-scoped, no leak).
  - History cursor/filter tests: `has_more`/`next_cursor` correct across two pages; equal
    `created_at` rows paginate without dup/skip (id tie-breaker in cursor); **a row inserted
    between page 1 and page 2 does not duplicate or skip** an already-returned row (keyset
    invariant); `category` filters to the right `entry_type` set server-side (incl. `adjustments`
    returning a `dispute_reinstated` row); out-of-range `limit` returns **422**.
  - `/auth/me` test: response includes `id` and `created_at`.
  Run `pytest` in `srt-backend`. Manually: `AUTH_MODE=dev` app, seed a `CreditLedgerEntry`,
  `curl /api/billing/history`.
- **Frontend:** add a `BillingScreen` vitest (renders account card, usage bar, history table,
  receipt link; empty-history state). Also cover the two new stateful flows:
  - **Session-specific confirmation:** with a `session_id` prop set (App captured it from the
    return URL), poll calls `getBillingConfirm(sessionId)`; when it resolves `applied:true`,
    balance **and** ledger refetch (new row appears); on timeout the confirming→timeout state shows.
  - **Load more / filter:** "Load more" calls with `before: next_cursor` and appends the next page
    (rows accumulate); changing the category filter drops the cursor and **replaces** rows (no
    stale append).
  Run `npm run test` + `npm run typecheck` in `srt-frontend`.
  Manually: `npm run dev`, sign in (dev), open Billing tab — verify balance, gradient bar,
  and history render; light + dark mode.
- Run `/verify` to drive the billing flow end-to-end before committing.

## Out of scope
Subscriptions, CSV export, the History-panel `MOCK_QUOTA` bug (bug 1) and the user-menu
click-away bug (bug 3) from `note.md` — separate follow-ups (the shared `QuotaBar` makes bug 1 trivial).
