# Home Page — Pricing Section

Design for the landing `#pricing` section. Reflects the 3-tier minute-based
credit-pack model in [pricing-plan.md](./pricing-plan.md).

## Where it lives

`srt-frontend/src/LandingScreen.tsx`, existing `#pricing` `<section>`
(currently a stub: `MonoLabel` + `<h2>` + one `<p>`, ~lines 184-197). Replace
the stub body with a plan grid. Keep the `MonoLabel` eyebrow + `<h2>` header.

Stack: Vite + React + TS, Tailwind v4 (CSS-first, theme tokens in
`src/index.css`). No router — CTAs use `primaryAction` (Google login) already
defined in the file. Reuse `Card` / `Button` from `src/ui.tsx`,
`MonoLabel` for the eyebrow.

## Layout

```
                    simple pricing            <- MonoLabel
        Start free. Pay once when you need more.   <- h2
   Buy minutes, not a subscription. Metered by source length.  <- sub

  ┌───────────┐  ┌───────────┐  ┌───────────┐   <- 3 cards
  │  Free     │  │ Small pack│  │ Large pack│
  │  $0       │  │  $3.99    │  │  $29.99   │
  │           │  │           │  │  BEST VALUE│  <- accent ribbon
  │ 20 min    │  │ 100 min   │  │ 1000 min  │
  │           │  │ $0.040/min│  │ $0.030/min│  <- unit price
  │ 9 langs   │  │ 9 langs   │  │ 9 langs   │
  │ [Start    │  │ [Buy      │  │ [Buy      │
  │  free]    │  │  100 min] │  │  1000 min]│
  └───────────┘  └───────────┘  └───────────┘

     no card for free · one-time payment · no auto-renew   <- reassurance strip
```

Grid: `grid gap-6 md:grid-cols-3` inside `mx-auto max-w-6xl`. On mobile stack
single column. Large pack card visually emphasized (accent border + "Best
value / 25% off" ribbon).

## Card contents (data-driven)

Define an inline array, map to `Card`:

| field | Free | Small | Large |
|-------|------|-------|-------|
| name | Free | Small pack | Large pack |
| price | $0 | $3.99 | $29.99 |
| minutes | 20 min | 100 min | 1000 min |
| unit | — | $0.040/min | $0.030/min |
| badge | — | — | Best value · 25% off |
| features | 9 languages · real trial | 9 languages · ~1–2 shows | 9 languages · ~25 shows |
| cta label | Start free | Buy 100 min | Buy 1000 min |
| accent | no | no | yes |

Optional: show "log in required" caption; logged-out demo mention links to hero
demo.

## CTA wiring

- **Free card** → `primaryAction` (existing). Logged-out = Google login;
  logged-in = open app.
- **Paid cards** → checkout. Current `startCheckout()` (`api.ts:163`) hits
  `POST /api/billing/checkout` with **no pack argument** — backend must accept a
  pack/price selector first (see auth-billing-status.md gaps). Until then, wire
  paid CTAs to `primaryAction` too (sign up → billing tab) and finish real
  checkout after backend supports packs.

Add a `pack` param to `startCheckout(pack?: "small" | "large")` when backend
ready.

## Styling tokens (dark-mode free)

Use theme classes: `bg-surface`, `bg-surface-subtle`, `border-border`,
`text-ink`, `text-ink-muted`, `text-accent`, `.gradient-text` for price. Accent
ribbon: `bg-accent text-white` or `bg-accent-soft text-accent`. Match existing
section padding `px-5 py-24` and `scroll-mt-24` (anchor offset).

## Localization

Only demo tagline localized today (`demoLine.ts` pattern, 9 langs). Pricing copy
= hardcoded English for now. If localizing later, follow the same typed
`Record<LangCode, ...>` map, not an i18n lib. Prices/minutes are numbers — only
labels ("Best value", "Buy X min", feature lines) need translation.

## Scope note

Visual section can ship now against the **existing** single-price checkout
(both paid buttons → same $X) as a placeholder. Real 2-pack pricing needs the
backend credit-pack work first.
