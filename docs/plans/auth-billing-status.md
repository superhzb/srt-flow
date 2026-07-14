# Auth & Billing — Current State (wrap-up)

Snapshot of what's built today, what works, and what's missing for the
minute-based credit-pack model in [pricing-plan.md](./pricing-plan.md).

## Architecture

FastAPI mono-app (`srt-backend/src/srt_backend/app.py`) composing packages:
`pkg-auth`, `pkg-billing`, `pkg-job-orch` (owns DB + canonical `User`). One
`AppStore` (`app_store.py`) implements both `UserStore` + `BillingStore`
protocols against shared SQLite. Frontend: Vite + React + TS SPA, no router,
session held in a root `useState` (no context/store).

## AUTH — done, works

| Piece | State | Location |
|-------|-------|----------|
| Google OAuth 2.0 (OIDC id_token) | ✅ only provider | `pkg-auth/google.py` |
| Dev bypass (`AUTH_MODE=dev`, ENV=dev only) | ✅ | `dependencies.py` |
| Session = JWT HS256 in httponly cookie `srt_session` (7d TTL) | ✅ | `tokens.py` |
| CSRF state cookie for OAuth | ✅ | `google.py` |
| `GET /api/auth/me` · `POST /logout` · `GET /paid-check` | ✅ | `router.py` |
| `require_tier` gate (402 Upgrade), admin allowlist (403) | ✅ | `dependencies.py` |
| Sticky-paid upsert (never downgrades on re-login) | ✅ | `app_store.py:39-55` |
| Frontend: `AuthScreen` (diag tab), `getMe()`/`googleLoginUrl()` | ✅ | `AuthScreen.tsx`, `api.ts` |

Tier claim in JWT is informational — tier always re-read from DB per request.
`User` model: `{id, email, tier("free"|"paid"), google_sub, created_at}`
(`pkg-job-orch/models.py:87-94`).

**Auth = essentially complete for prototype.** No known gaps for shipping.

## BILLING — partial, binary tier flip only

What works:
- `POST /api/billing/checkout` → Stripe Checkout Session (`mode="payment"`,
  `quantity=1`, single `STRIPE_PRICE_ID`) or Payment Link fallback.
  `api.py:74-101`.
- Webhook `POST /api/billing/webhook`: custom HMAC signature verify, handles
  `checkout.session.completed` + `async_payment_succeeded`, idempotent via
  `ProcessedEvent` ledger. `api.py:141-249`.
- On paid webhook → **flips `user.tier="paid"`**. That's the only side effect.
- Frontend `BillingScreen.tsx`: free/paid binary UI, Upgrade → Stripe redirect,
  polls `getMe()` post-checkout to detect tier flip.

## Gaps for credit-pack model

Current billing is a **binary free/paid flip from one one-time payment**. The
new pricing (20 free min → 100/1000 min packs) needs:

1. **Credit balance + ledger** — `User` has no minutes/credit field. Add
   `purchased_minutes: int` (additive, non-expiring) + append-only ledger table
   (credits/debits, idempotent per key); free 20 min is a **monthly** grant,
   tracked separately. `pkg-job-orch/models.py` + new migration under
   `migrations/versions/`.
2. **Multiple packs** — checkout hardcodes one price, `quantity=1`. Need a
   pack→price_id map (small/large) and pass selection through
   `POST /api/billing/checkout`. `pkg-billing/config.py` + `api.py`.
3. **Webhook credits minutes** — must add purchased minutes to balance, not
   flip a boolean. Map Stripe price/pack → minutes. Idempotency key = **Stripe
   Checkout Session ID** (unique constraint), not `event_id` — fulfill once per
   session. Refunds via `refund.created` keyed by **Refund ID** (proportional
   minutes, handles partials); disputes via `dispute.created` (negative) +
   `dispute.funds_reinstated` (positive), keyed by dispute id. Balance may go
   negative.
   `apply_paid_webhook_once` in `app_store.py` (+ `ProcessedEvent`/ledger schema).
4. **Minute metering on jobs** — `Job` persists no duration. Compute source
   minutes from SRT cue end-timestamps, persist on job row.
   `pkg-job-orch/models.py` + job create path.
5. **Real quota/debit gate** — `check_quota` (`api.py:104-119`) counts *jobs*
   (default 10), is **not called anywhere**, and its backing
   `usage_count_this_period` is a **stub returning 0**. Job creation
   (`POST /api/jobs`) is still **unauthenticated dev-mode** (trusts
   `dev_user_id`). Need: gate behind `get_current_user`; check balance at
   submission (reject 402 if source-minutes > free_remaining + purchased);
   **debit on success only** (failed/cancelled jobs cost nothing).
6. **Balance/pack UI** — `BillingScreen` shows only free/paid. Add minutes
   remaining, pack selection, usage meter. `BillingScreen.tsx` + `api.ts`.

## Suggested order

0. Reset existing `tier="paid"` rows to free on switchover (drop bypass).
1. Add `purchased_minutes` + ledger to `User` + migration; free = 20 min/month
   (UTC). Ledger unique on session_id; supports negative (refund) entries.
2. Persist source-minutes on `Job` (max cue end-ts, ceil to whole minute).
3. Wire real auth into `POST /api/jobs`: balance check at submit, debit on
   success (closes biggest hole: job create is currently open).
4. Multi-pack checkout + webhook minute crediting.
5. Frontend balance/pack UI + landing pricing section
   ([home-pricing-section.md](./home-pricing-section.md)).

Steps 1-3 are the real prototype blockers (metering + closing the open job
endpoint). 4-5 make it sellable.

## Key files

`pkg-billing/src/pkg_billing/{api,config}.py` ·
`pkg-job-orch/src/pkg_job_orch/{models,routes}.py` (+ new migration) ·
`srt-backend/src/srt_backend/app_store.py` ·
`srt-frontend/src/{BillingScreen,api}.tsx/ts`
