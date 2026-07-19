# Google Ads Test Plan — srt-flow

**Product:** SRT subtitle translator. Credit model — free monthly minutes + credit packs ($3.99 / $29.99).
**Goal:** Test-promote the web app via Google Ads and measure whether paid acquisition is viable.

> **Blocker found:** Privacy policy currently states **"no third-party advertising or analytics"** (`srt-frontend/src/contentPages.tsx`). A Google Ads conversion tag is third-party. Resolve this before spending (see Phase 0).

---

## Phase 0 — Legal + measurement prep (do first)

1. **Resolve privacy conflict.** Either:
   - (a) Update privacy/cookie policy to disclose Google Ads + add a consent banner (GDPR / PIPEDA — Bayard Canada), **or**
   - (b) Use Google Ads **Enhanced Conversions / server-side** + **Consent Mode** so no client cookie fires pre-consent.
   - Recommended: (a) + (b) together.
2. **Define conversion events.** 1 primary + secondary:
   - Primary: first paid credit purchase (checkout success in `BillingScreen`).
   - Secondary: signup, first translation run.
3. **Pick tracking method.** First-party `/api/events` already exists. Cleanest: fire Google Ads conversion **server-side** from backend on checkout success → avoids more client-side third-party JS, respects privacy stance. Alt: `gtag` on frontend (needs consent banner).

## Phase 1 — Account + tags

4. Create Google Ads account + conversion actions (signup, purchase with value = pack price).
5. Wire conversion firing (server-side upload API or gtag). Test with Google Tag Assistant.
6. Verify events land in Ads before spending.

## Phase 2 — Landing page

7. Don't send ads to the generic `LandingScreen` home. Build/confirm a focused landing per use-case: "Translate SRT subtitles to [language] in minutes." Clear CTA → free minutes.
8. Match ad copy → landing headline (Quality Score). Show price, free tier, sample.
9. Free monthly minutes = the hook. Lead with "Try free."

## Phase 3 — Campaign structure

10. **Campaign type: Search** (high intent) for the test — not Display / PMax.
11. Ad groups by intent cluster:
    - "srt translator", "translate subtitles", "subtitle translation online"
    - Language pairs: "translate subtitles to spanish/french/japanese"
    - Competitor/tool: "[competitor] alternative"
12. Match types: phrase + exact. Add negatives ("jobs", "how to manually"; "free" only if avoiding freeloaders).
13. 3–4 responsive search ads per ad group.

## Phase 4 — Budget + bidding

14. Test budget: **$20–50/day for 2–4 weeks** (~$300–1000 total). Need ~15–30 conversions before optimizing.
15. Bidding: start **Manual CPC** or **Maximize Clicks** to gather data → switch to **Maximize Conversions / tCPA** once conversion volume exists.
16. Geo: start English CA/US. Use ad scheduling if budget tight.

## Phase 5 — Launch + measure

17. Launch. Check daily the first week (search terms report → add negatives).
18. Track funnel: click → signup → first translation → purchase. Admin analytics funnels already exist — reuse.
19. Compute CAC = spend / paid conversions. Compare vs pack value ($3.99 low, $29.99 real target). The $3.99 pack alone won't cover CAC — target $29.99 buyers or repeat purchase.

## Phase 6 — Iterate

20. After 2 weeks: kill losing keywords/ads, scale winners, refine landing. Decide go/no-go on CAC vs LTV.

---

## Watch-outs

- $3.99 pack << realistic Google CPC in this niche (likely $1–4/click). Need high conversion or upsell to $29.99, or ads lose money by design — acceptable for a *test*, but plan the metric.
- Prerendered site (`make build`) required for landing SEO/tags — **not** `make dev`.
