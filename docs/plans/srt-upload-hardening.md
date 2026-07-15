# SRT Upload — Failure Modes & Hardening Plan

Flow: `UploadFlow` (client validate) → `POST /srt/prepare` (`_decode_srt` → `parse` → `detect`) → configure → billing/worker.

Key files:
- `srt-frontend/src/App.tsx:61` `validateFile`, `:794` `UploadFlow`, `:185` `parseEntry`
- `srt-backend/src/srt_backend/routes_srt.py` (`_PrepareLimiter`, `_decode_srt`, `parse_srt`, `prepare_srt`)
- `srt-backend/pkg-srt-services/src/pkg_srt_services/api.py` (`parse`, `_parse_block`, `build_stacked_srt`, `serialize`)
- `srt-backend/src/srt_backend/detection.py` (`detect`)

## Stage 1 — Client validation
Checks: `.srt` suffix, size > 0, ≤ 4 MiB, `MAX_BATCH = 20`.

| Risk | Current | Gap |
|---|---|---|
| Wrong ext | rejected client + server | ok |
| Empty / > 4 MiB | rejected both sides | ok |
| > 20 files | capped, `"N rejected (maximum 20)"` | ok |
| `.srt` name but binary/non-SRT body | passes client | server catches (decode/parse) — ok |
| Batch of 20 → each fires `/prepare` | — | 20 files == rate limit 20/600s; any retry → 429 (see Stage 2) |

## Stage 2 — Transport / rate limit (`_PrepareLimiter`)
- Limit `PREPARE_RATE_LIMIT=20` per `600s` per client key. `Retry-After` header set. Good.
- **Gap: MAX_BATCH (20) equals rate limit (20).** Full batch consumes entire window. One `retry()` or re-upload → `429 "prepare request limit exceeded"`. Frontend shows error, no auto-backoff.
  - Fix: raise limit above MAX_BATCH, or per-file idempotency, or client queue + backoff on 429.
- Proxy key (`_client_key`) trusts `x-forwarded-for` only from configured proxies — good. Misconfigured `PREPARE_TRUSTED_PROXIES` in prod → all users share one key → shared 429. Verify deploy env.
- `/parse` NOT rate-limited (only `/prepare`). Frontend uses `/prepare`, so ok, but `/parse` open to abuse.

## Stage 3 — Decode (`_decode_srt`)
- UTF-8 **strict** only. BOM handled downstream in `parse`.
- **Gap: real SRTs often Windows-1252 / Latin-1 / UTF-16.** Those → `400 "file is not valid UTF-8"`. No charset sniff/fallback (e.g. `charset-normalizer`). High false-reject rate on real user files.
- `await file.read()` loads full body before size check — bounded by Starlette spool, acceptable at 4 MiB.
- BOM-only / whitespace-only file passes non-empty byte check → `parse` raises `"empty SRT payload"` 400. ok.

## Stage 4 — Parse (`parse`, `_parse_block`)
Regex: `_TIMESTAMP` allows `,`/`.`, 1-2h digits. Blocks split on blank lines.

**Silent-corruption edge cases (no error, wrong output):**
- **Missing blank line between cues** → whole file = 1 block. lines[0]=index, lines[1]=timespan, rest (incl next cue's index/timespan) folded into one giant `text`. No error, garbage result.
- **Timestamps not sanity-checked**: `99:99:99,999` valid to regex. `start > end`, zero-duration, overlaps all pass. No `start <= end` check.
- **Duplicate / non-sequential indices** accepted. `build_stacked_srt` keys `target_texts[lang].get(cue.index)` by index → duplicate indices collide, wrong translated line mapped. Real bug.

**All-or-nothing rejection:**
- One bad block fails whole file (`ParseError` → 400). Empty-text cue common in real SRTs → whole file rejected. No skip-and-warn / lenient mode.
- Block < 2 lines → `"cue block too short"`.

**Passed-through untranslated:**
- Markup `<i>`, `{\an8}`, `\h`, `<font>` kept as text → translated literally, tags mangled.

**Scale:**
- No cap on cue count. 4 MiB of tiny cues = thousands of cues → unbounded downstream translation cost/time. Detection samples 40 (bounded), but worker + per-language billing not. Verify cost cap exists.

## Stage 5 — Detection (`detect`)
- Below `_CONFIDENCE_FLOOR=0.5` or unmappable → `lang=None` → UI leaves source unselected (by design). Confirm UI blocks submit until source chosen.
- Short/mixed-language sample → misdetect. User can override — ok.
- Only 7 lingua langs loaded; source outside set → None. Expected.

## Stage 6 — Client async handling (`parseEntry`)
- `generation` + `status`/`id` guards against stale-response races on retry. Good.
- Errors → per-entry `status:"error"` + `errMessage(error, "failed to parse file")`, retryable. Good.
- Multiple files parse concurrently → all hit `/prepare` → Stage 2 429 risk.

## Priority Gaps (ranked)
1. **MAX_BATCH == rate limit** → guaranteed 429 on retry/large batch. (Stage 2)
2. **UTF-8-only decode** → mass false-reject of real Latin-1/UTF-16 SRTs. (Stage 3)
3. **Missing-blank-line & duplicate-index** → silent wrong output, not errors. (Stage 4)
4. **No timestamp sanity** (start > end, zero-duration). (Stage 4)
5. **All-or-nothing on empty-text cue** — reject whole file for one blank cue. (Stage 4)
6. **No cue-count cap** → unbounded cost/time downstream. (Stage 4 — verify billing)
7. **Subtitle markup translated literally.** (Stage 4)

## Suggested order
Start 1 + 2 (highest user impact, low risk), then 3 + 4 (parser correctness).


Quick update pour Naviga Coupon: 
- Naviga Coupon Production has been merged and deployed, test OK. 
- GetPreflight endpoint added, test OK. 

- The coupons I have are too old to test it always failed on Naviga. I will ask Nina to get some new coupon to test on staging. If it works, I will invite you and Camille for production test. 
- I will need to add 'batch' in Naviga Coupon project, like 'one-day-one-batch' as we talked about. 