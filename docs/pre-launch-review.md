# srt-flow — Pre-Launch Review & Compliance Plan

_Reviewer: senior-PM lens · Date: 2026-07-18 · Target: public test launch_

## What the app is (as-built)

- **Product:** SRT subtitle-file translator. Upload `.srt` → auto-detect source → LLM translates into up to 9 languages → bilingual output. Angle: "learn a language from the videos you already love."
- **Host:** `https://app.srt-flow.com` (FastAPI serving prerendered React, fronted by Cloudflare tunnel).
- **Auth:** Google OAuth (OpenID Connect) only. No passwords. JWT in HttpOnly/Secure/SameSite=lax cookie, 7-day TTL.
- **Billing:** Stripe Checkout, one-time credit packs (no subscription). Free = 30 min/mo (no card); $3.99 / 100 min; $29.99 / 1000 min. Signed webhooks, append-only credit ledger.
- **LLM provider:** **DeepSeek** (`api.deepseek.com`, China-based). User subtitle text is sent there.
- **Analytics:** first-party only, no 3rd-party SDK. Persistent `anon_id` + rotating `session_id` in localStorage; events → `/api/events`.
- **PII stored:** email + Google subject ID (SQLite). Stripe holds payment data.
- **Uploads:** stored on local disk `{STORAGE_ROOT}/{user_id}/{job_id}/`. 4 MiB cap, `.srt` only.
- **Abuse controls:** in-memory rate limits (20/window uploads, 60/min events), path-traversal guards. No public/shareable UGC.

## Key file paths

| Area | Path |
|---|---|
| Public routes (no legal routes) | `srt-frontend/src/routes.ts` |
| Footers (no legal links) | `srt-frontend/src/LandingScreen.tsx:269`, `srt-frontend/src/TranslatePage.tsx:169` |
| DeepSeek config | `srt-backend/pkg-llm-backend/src/pkg_llm_backend/config.py`, `llm.py` |
| Stripe billing | `srt-backend/pkg-billing/src/pkg_billing/` |
| Auth | `srt-backend/pkg-auth/src/pkg_auth/google.py` |
| File storage / retention gap | `srt-backend/pkg-file-upload/src/pkg_file_upload/api.py` |
| Analytics | `srt-frontend/src/analytics.ts`, `srt-frontend/src/clientStorage.ts` |

---

## 🔴 Launch blockers

1. **No Privacy Policy.** Required by PIPEDA + Quebec Law 25, GDPR (EU visitors), CCPA (CA). Stripe & Google OAuth ToS both require one. Must name sub-processors: **DeepSeek, Stripe, Google**. Describe PII (email, Google sub, IP, uploaded content, analytics IDs).
2. **No Terms of Service.** Taking money with no ToS = no liability cap, no refund policy, no as-is disclaimer, no acceptable-use clause.
3. **No Contact / support mechanism.** "Contact support" is error copy only — no address. Required in practice (Stripe visible-contact + Law 25 named privacy contact).
4. **DeepSeek cross-border transfer (China).** No adequacy decision for China under GDPR/Law 25 → needs lawful-transfer basis + legal read if EU/UK/EEA traffic expected. Verify DeepSeek API terms on training-on-input; disclose retention.
5. **No retention/deletion for uploaded SRT + job data.** Files persist indefinitely on disk (only analytics events auto-scrub identity at 365 days). Add TTL purge job + user data-deletion path (GDPR/CCPA/Law 25 right to erasure).

## 🟡 Strongly recommended

- **About page** — trust/conversion + SEO E-E-A-T. Not legally required.
- **Refund policy** in ToS (prepaid credits → first refund request will be ad-hoc otherwise).
- **Cookie/consent decision.** First-party only helps, but persistent `anon_id` joins to logged-in user server-side → disclose; evaluate consent banner for EU ePrivacy.
- **Acceptable-use clause** — SRT files often copyrighted; user warrants rights, you disclaim.
- **Confirm tax/currency.** Pricing is USD; Canadian merchant → verify tax handling.
- **Rate limiters are in-memory per-process** — move to shared store before scaling to multiple instances.

## 🟢 Lower risk (confirmed OK)

- No passwords (OAuth only). No 3rd-party analytics trackers. Auth cookies hardened.
- Upload cap + type check + rate limits + path-traversal guards present.
- No public/shareable user content; outputs auth-gated per user.

---

## Contact / About decision

- **Contact page — YES, effectively mandatory.** Payments + PII + Law 25 named contact. Minimum: support email + short form. Add `support@srt-flow.com`, surface in-app + on failure cards.
- **About page — YES, recommended (not mandatory).** Trust for a paid app + SEO.

**Minimum footer before launch:** `Privacy Policy · Terms · Contact · © 2026 srt-flow` (About optional).

---

## Action checklist

- [x] Draft + publish Privacy Policy (sub-processors: DeepSeek, Stripe, Google) — `docs/legal/privacy-policy.md`, live at `/privacy/`
- [x] Draft + publish Terms of Service (liability, refunds, as-is, acceptable-use) — `docs/legal/terms-of-service.md`, live at `/terms/`
- [x] Contact page + `support@srt-flow.com`, surface on failure cards — `/contact/`, `FailureCard.tsx`
- [x] Implement SRT/job retention TTL + purge job — `pkg_job_orch/retention.py`, 30-day TTL, daily loop wired in lifespan (env `JOB_RETENTION_DAYS`, `RETENTION_INTERVAL_SECONDS`)
- [x] Implement user data-deletion path — `DELETE /api/account` + `pkg_job_orch/erasure.py`
- [x] Add legal routes to `routes.ts` + links in both footer components — `LegalLinks.tsx`, `contentPages.tsx`
- [x] About page — `/about/`
- [x] Disclose `anon_id` in Privacy Policy (§ cookies/local storage)
- [x] Confirm Stripe merchant-of-record + tax/currency — small-supplier, no GST/HST reg yet; Stripe Tax monitoring; USD→CAD auto-convert (see conversation notes)
- [ ] **HUMAN:** Legal read on DeepSeek China data transfer; verify DeepSeek retention/training terms (EU traffic) — disclosed + upload-warning in policy §3; lawyer sign-off still advised
- [ ] **HUMAN:** Cookie/consent banner decision for EU ePrivacy (`anon_id` is first-party + disclosed; banner recommended at scale, deferred for test launch)
- [ ] Move rate limiters to shared store (pre-scale)

### Human sign-off still required before launch
1. Review/approve the drafted Privacy Policy + ToS copy (liability cap set at greater of 90-day spend or CAD $50 — confirm).
2. DeepSeek/China + EU: accept disclosed risk or get counsel read.
3. EU cookie-consent banner: yes/no.
4. Verify DMARC propagation (record added, `p=none`).
