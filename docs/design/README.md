# srt-flow — Design Reference

Evergreen design documentation for **srt-flow**, an SRT subtitle translation web app.
These docs describe how the system works **now** (present tense), with pointers to the
implementing code as `path/file:symbol`. They replace the point-in-time plans that
previously lived under `docs/plans/`.

> Keep these current: when a subsystem changes materially, update its doc in the same PR.

## Contents

| # | Doc | Covers |
|---|-----|--------|
| 01 | [System Architecture](01-architecture.md) | Monorepo/uv-workspace layout, FastAPI app wiring, DB layer, `pkg-file-upload` storage seam, in-process translation engine (`pkg-translator` + `pkg-llm-backend`, `LLM_BACKENDS`), `pkg-notification`, deploy/ops/CI, request flow, package map |
| 02 | [Auth & Admin](02-auth-admin.md) | Google OAuth login, JWT session cookie, `get_current_user`/`require_admin`, env-only admin allowlist, read-only SQLAdmin console |
| 03 | [Billing (money-in)](03-billing.md) | Credit packs from Stripe price metadata, checkout + webhook, session-keyed idempotent crediting, refunds/disputes, `/history` + `/confirm`, receipt enrichment, pricing/account UI |
| 04 | [Credits & Metering](04-credits-metering.md) | Append-only credit ledger model, source-minute metering, submit-time 402 gate, charge-on-success debit, idempotency keys |
| 05 | [SRT Processing](05-srt-processing.md) | Parse/validate, Lingua language + bilingual detection, `carried_langs`, translation pipeline, upload/configure UX, hardening backlog |
| 06 | [Jobs & Failure Handling](06-jobs.md) | Job lifecycle & state machine, in-process worker, progress folding, error taxonomy, retry endpoint, restart recovery, failure UX |
| 07 | [Analytics / Events](07-analytics.md) | Generic `event` table, server + client emitters, event catalog, admin analytics view, retention |
| 08 | [SEO & Prerendering](08-seo.md) | Meta tags, build-time prerender + sitemap, per-language landing routes, static serving, off-page ops checklist |

## Reading order

Start at **01** for the system map, then jump to whichever subsystem you're working on.
Money flows split across two docs: **03** owns money-in (Stripe/purchases/refunds), **04**
owns the ledger model + usage metering.

## Related in-repo docs

- `srt-backend/DESIGN.md`, `srt-frontend/DESIGN.md` — service-level design notes
- `srt-backend/pkg-*/README.md` + `AGENTS.md` — per-package detail
- `README.md` (root), `ops/README.md` — setup and operations
