# Pricing Plan — Prototype

Currency: **USD**. All prices, costs, and margins below are USD.

## Goal

Low entry price to test willingness to pay, tiered discount to lift average
order value. Three tiers. Whether it works is the team's call later — this plan
just makes sure the data is captured (see below).

### Data to capture

Record enough for the team to judge demand later. No thresholds here — just
make sure these are queryable:

- **Purchases**: user, pack (small/large), amount, Stripe session id, timestamp.
- **Balance depletion**: when a user's purchased balance hits 0 (so repurchase
  vs depletion can be measured).
- **Repurchases**: any second+ purchase, derivable from the purchase log above.
- **Usage**: minutes debited per job (source duration), per user, timestamped.
- **Refunds/disputes**: reversal entries with reason + timestamp.
- **Funnel**: sign-up, checkout started, checkout completed (for conversion).

The credit ledger + job rows below already carry most of this; the point is
don't drop any of it.

## Pricing structure

| Tier | Price | Quota | Unit / min | Notes |
|------|-------|-------|-----------|-------|
| **Free (logged out)** | $0 | pre-translated fake demo | — | Showcase only, converts visitors to sign-ups |
| **Free (logged in)** | $0 | 20 min / month | — | Real trial, resets monthly (~1–2 episodes) |
| **Small pack** | $3.99 | 100 min | $0.0399 | Light users, impulse-buy threshold |
| **Large pack** | $29.99 | 1000 min | $0.03 | Heavy users, ~25% off |

Free allowance is **monthly recurring** (matches existing
`free_tier_monthly_limit`, `config.py:33`) — resets at the start of each
**UTC** calendar month, does not roll over. A job's month is owned by its
**submission time** (UTC), consistent with the submit-time balance check — a job
submitted before UTC midnight but completing after still counts against the
submission month. Purchased pack minutes are **additive and
do not expire** (separate balance from the free monthly grant).

## Cost & margin

⚠️ **Model-cost margin only** — the table below covers translation compute, not
payment processing. See fee-adjusted row.

Compute estimate: DeepSeek Flash (1M input cache-miss $0.14 / 1M output $0.28),
single-language translation ~**$0.0001/min**, worst case all 9 languages
~**$0.0009/min**. This is an **unmeasured estimate** — it does not yet account
for measured tokens/subtitle-minute, prompt overhead, batching, retries, or
validation calls, and subtitle density varies. TODO: measure input/output
tokens per minute on a sample SRT set and replace with a p50/p90 range.

Stripe US pricing: **2.9% + $0.30** per domestic-card charge.

| Pack | Revenue | Compute (worst) | Stripe fee | Net | Net margin |
|------|---------|-----------------|-----------|-----|-----------|
| Small $3.99 | $3.99 | ~$0.09 | ~$0.42 | ~$3.48 | ~87% |
| Large $29.99 | $29.99 | ~$0.90 | ~$1.17 | ~$27.92 | ~93% |

Payment processing (not compute) is the dominant marginal cost of the small
pack. International cards, currency conversion, refunds, disputes, and sales tax
reduce this further. Margin still strong; pricing driven by value + conversion
psychology, not cost-constrained.

## Billing model — credit ledger

The current code is a **binary tier flip** (one `STRIPE_PRICE_ID`, webhook sets
`user.tier="paid"` permanently, paid users bypass quota) — see
[auth-billing-status.md](./auth-billing-status.md). That **cannot** represent
additive, consumable, repurchasable packs. It must be replaced with a balance +
ledger:

- **Balance**: add `purchased_minutes: int` (or a derived balance) on `User`,
  separate from the monthly free grant.
- **Ledger**: append-only table of credits (purchases) and debits (jobs), each
  row keyed for idempotency. Balance = sum(ledger) or a cached column kept in
  sync within the same transaction.
- **Two packs**: map **Stripe price → minutes via trusted price metadata**
  (read from the Stripe object, never client input). Small price → +100,
  large → +1000.
- **Credit on webhook**: on `checkout.session.completed` /
  `async_payment_succeeded` with `payment_status=="paid"`, append **one** credit
  row. **Idempotency key = the Stripe Checkout Session ID**, not `event_id` —
  Stripe can fire fulfillment multiple times (and concurrently) per session, so
  fulfill **once per Session** (per Stripe guidance). The ledger's purchase key
  gets a **unique constraint on `session_id`**; `event_id` is retained only for
  audit. (Current `ProcessedEvent` uniques `event_id` but leaves `session_id`
  unconstrained — `models.py:97` — that must change.)

### Refunds & disputes

Auto-reverse via **negative** ledger entries. Keying matters — a charge can be
refunded multiple times (partials) and a dispute can be reinstated, so a single
entry keyed by charge/dispute id is wrong:

- **Refunds**: listen to **`refund.created`**, key each negative entry by the
  **Refund ID** (idempotent, so partial + later refunds each post once). Minutes
  reversed = **proportional to refund amount** (`refund_amount / pack_price ×
  pack_minutes`, ceil). A full refund reverses the whole pack.
- **Disputes**: `charge.dispute.created` → negative entry keyed by **dispute
  id**. If later won, **`charge.dispute.funds_reinstated`** → a **positive**
  entry keyed by the same dispute id (reinstatement), idempotent so it can't
  double-apply. Never double-reverse a purchase that was both refunded and
  disputed — each Stripe object id keys exactly one entry.

If reversed credits were already consumed, balance goes **negative** — new jobs
blocked (402) until ≥ 0. Manual admin adjustment can post negative entries
through the same ledger.

One-time payments (`mode="payment"`), **not** subscriptions — avoids **dunning
and cancellation** CS load (refunds/disputes still exist and are handled above,
per the reversal policy). Repurchase when depleted (credit-pack model) is what
the purchase log captures for later analysis.

### Migrating existing `tier="paid"` users

The old model left users flipped to `tier="paid"` (unlimited bypass). On
switchover: **reset them to free** — remove the tier bypass, treat as free
(20 min/month, 0 purchased). Assumes these are test users, no real payments
taken. If that assumption is wrong for any row, grant an opening balance
manually instead. Do not leave the bypass live — grandfathered unlimited users
never generate purchase/usage data, leaving gaps in the metrics.

## Metering & debit transaction

Quota metered by **source file duration** (not processing time). Spec:

- **Duration**: max cue end-timestamp of the source SRT, **rounded up to the
  next whole minute** (ceil). Persist computed minutes on the `Job` row at
  creation (currently not stored — `Job` has no duration field).
- **Charge on success only.** No debit at submission. On job completion, append
  a debit row for the source-minutes. Failed or cancelled jobs cost the user
  **nothing** (no debit, no refund logic needed).
- **Insufficient balance**: checked at **submission** against
  `free_remaining_this_month + purchased_minutes`. If source-minutes exceed
  available, reject with 402 before the job runs. (Free minutes consumed first,
  then purchased.)
- **Concurrency**: the submission check is a soft gate; because charge is on
  success, worst case is a small overrun when multiple jobs submit against the
  same balance simultaneously. Acceptable at prototype scale (overrun = cents).
  Debits apply atomically per-job within a transaction; if we later tighten,
  add a reserve step — not needed now.
- **Enforcement gap**: `check_quota` currently counts *jobs*, is **never
  called**, and `usage_count_this_period` is a stub returning 0; job creation
  (`POST /api/jobs`) is still unauthenticated dev-mode. Real gate must move
  behind `get_current_user` and debit minutes. This is the biggest hole — see
  status doc step order.

## Logged-out demo

Logged-out users see a **pre-translated fixed demo**, not a live call. Zero
cost, zero abuse risk. Showcase + sign-up funnel only.

## Deliberately NOT doing yet

- **Subscriptions** — wait for repurchase data to prove demand.
- **Per-language exact metering** — per-minute is simple and sufficient.
- **Rollover of unused free minutes, credit expiry** — packs don't expire; free
  resets monthly, no rollover. Revisit later if needed.
- **More tiers / API / enterprise** — later iteration.

See also: [auth-billing-status.md](./auth-billing-status.md) (current state +
implementation order), [home-pricing-section.md](./home-pricing-section.md)
(landing UI).
