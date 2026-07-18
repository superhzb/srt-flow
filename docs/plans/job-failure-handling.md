# Job Failure Handling — Debuggability & Friendly UX

Plan to improve what happens when an SRT translate job fails, on two axes:
**backend** (make failures debuggable and recoverable) and **frontend**
(friendly error messages, "not charged" reassurance, retry).

## Current behavior (baseline)

- Failure funnel is `_process_job` → `_mark_failed` in
  `srt-backend/pkg-job-orch/src/pkg_job_orch/orchestration.py`.
- `default_worker_client` collapses **every** backend error into
  `WorkerStreamError` → `error_kind="worker_stream"`, flattening the cause to
  `str(exc)` (`orchestration.py:208-209`). Only `internal` and `landing` are
  distinguished. The real stack trace lives solely in logs via
  `logger.exception`.
- **Credits are debited only on success** (`debit_job_once` inside
  `_land_results`, `orchestration.py:521`). A failed job is never billed — no
  refund path needed or present.
- **No automatic retry** and **no manual retry** endpoint/UI. The only recovery
  is starting a new translation (full re-upload). `input.srt` is retained in
  storage, so replay is possible in principle.
- Frontend `FailureCard` (`srt-frontend/src/App.tsx:897`) shows the raw
  `error_kind` in mono-uppercase (user sees `WORKER_STREAM`) + a raw exception
  string, no retry, no billing reassurance. `JobsScreen` badges `failed` amber
  while the processing view shows red — inconsistent severity.

---

## Part A — Backend: debuggable & recoverable failures

### A1. Widen the error taxonomy
Classify the underlying cause at the raise site instead of one `worker_stream`
bucket.
- Add typed exceptions in `pkg_translator` (e.g. `UnsupportedLanguageError`,
  `NoBackendError`) subclassing the current `ValueError`/`RuntimeError` so
  existing behavior is preserved.
- In `default_worker_client` (`orchestration.py:159-221`), map cause → kind:
  `unsupported_language`, `worker_config`, `backend_unavailable`
  (network/timeout/rate-limit), keep `worker_stream` as catch-all. `internal`
  and `landing` unchanged. Note the kind string is assigned by the caller
  `_process_job` when it catches `WorkerStreamError` (`orchestration.py:427`),
  not inside `default_worker_client` — thread the classified kind through.
- **No `JobErrorKind` type exists in the backend today.** `error_kind` is a
  plain `str` column; `models.py:37` is `JobStatus`, not error kinds. Add a
  `JobErrorKind = str` alias with a docstring listing the valid kinds in
  `pkg-job-orch/src/pkg_job_orch/models.py` as the single source of truth, and
  keep the frontend union (`api.ts:44`) in sync.

### A2. Persist debug context on the `Job` row
Add columns via a **new Alembic migration** `0010_*.py` (prod path is Alembic —
`db.py` → `command.upgrade(cfg, "head")`; migrations live at
`pkg-job-orch/src/pkg_job_orch/migrations/versions/`, latest is 0009).
`create_all`/`init_schema()` is test-only. Use `op.add_column` (or `op.execute`
for raw ALTER):
- `error_detail: str | None` — exception class + repr (the info currently lost
  to `str(exc)`).
- `failed_target: str | None` — target language in flight when the job
  hard-failed; thread through `WorkerStreamError`. Distinct from existing
  `dropped_by_target` (0003), which is a JSON map of targets *soft-dropped* on
  an otherwise-successful/partial job (set on success paths at
  `orchestration.py:519, 553`); on a hard failure that column is never set.
  Keep the two separate — do not overload `dropped_by_target`.

Job model is `models.py:162-202`. `input.srt` + `worker` +
`src_lang`/`tgt_langs` are already persisted, so jobs are replayable; this adds
the *why*. `get_job` (`routes.py:166-216`) already surfaces `error` (line 196);
add `error_detail` + `error_kind` to its response model.

### A3. Structured failure log
Standardize the four `logger.exception` sites in `_process_job`
(`orchestration.py:426, 431, 440, 444`) to always include `job_id`,
`error_kind`, exception class, and target via `extra={...}` for reliable log
search by job id. Leave the two outer guard-rail sites (`orchestration.py:395`
`worker_loop`, `:564` `_mark_failed` failure-path) as-is — they fire when the
normal path already broke, have no meaningful `error_kind`, and already log
`job_id`.

### A4. Retry endpoint (serves both A & B)
`POST /api/jobs/{id}/retry` in `routes.py`:
- Ownership check + must be `status=="failed"` (else 409).
- Reset row to `pending`, clear `error`/`error_kind`/`error_detail`/
  `finished_at`, then `ctx.queue.put_nowait(id)`. Input already in storage — no
  re-upload. `attempts` increments naturally on next claim.
- Record a `job_retried` event.

### A5. Tests
- Failure-classification unit tests (each exception → expected kind).
- Retry-endpoint test (failed → pending → done).
- Assert the "no charge on failure" invariant.

---

## Part B — Frontend: friendly errors, reassurance, retry

### B1. Error-copy map
New `srt-frontend/src/errorCopy.ts`: `error_kind → { title, description,
retryable }`. E.g. `backend_unavailable` → "Translation service was temporarily
unavailable — please retry." (retryable); `unsupported_language` → "One of the
target languages isn't supported." (not retryable). Unknown kind → generic
fallback.

### B2. Rebuild `FailureCard` (`App.tsx:897`)
- Friendly **title** + **description** from the map (no raw `error_kind`
  headline).
- **"You weren't charged for this job."** reassurance line (backed by A5).
- Collapsible **"Technical details"** `<details>` with `error_kind` + raw
  `error`/`error_detail` for support.
- **Retry** button when `retryable`, calling B3.

### B3. `retryJob` client + wiring
- `api.ts`: add `retryJob(jobId)` → `POST /api/jobs/{id}/retry`; extend the
  `JobErrorKind` union with new kinds.
- On click: call `retryJob`, move the job back into the polling set (reuse
  existing `usePoll` terminal flow) so UI transitions failed → processing with
  no re-upload.

### B4. Severity consistency
`JobsScreen` `StatusBadge` (`JobsScreen.tsx:351`): color `failed` **red** to
match the processing view; surface the same friendly copy inline.

### B5. Tests
Component test: failed job renders friendly title + "not charged" + retry for a
retryable kind; hides retry for a non-retryable kind.

---

## Resolved decisions

1. **Retry cost** — unlimited retries, billed only on eventual success (already
   how debit-on-success works). No `attempts` cap. `attempts` increments
   naturally per claim, tracked for debug only.
2. **DB migration mechanism** — Alembic. New `0010_*.py` migration (see A2).

## Build order
B depends on A's new `error_kind` values and the retry endpoint. Recommend
landing **Part A first**, then Part B.
