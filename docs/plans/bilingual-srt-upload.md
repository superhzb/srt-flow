# Plan: Handle upload of an already-bilingual SRT

## Context

Users sometimes upload an SRT where **each cue already holds two languages on two
separate lines** — e.g. `test_files/1960-eleves-cours-francais.srt`:

```
1
00:00:00,000 --> 00:00:03,000
Est-ce qu'on fait un peu de français dans le restaurant?   ← line 1: fr
我们在餐厅里讲一点法语吗？                                      ← line 2: zh
```

Today this breaks silently:
- `detect(cues)` (`srt-backend/src/srt_backend/detection.py:83`) joins both lines and asks
  lingua once → a wrong / low-confidence single guess.
- The whole 2-line `text` is fed to the translator as one source segment
  (`build_segments`, `worker_client.py:169`) → both languages get translated → garbage.
- Billing still charges full `source_minutes × targets` (`credits.py:34`).

**Desired behavior (confirmed with user):**
1. Detect the file is bilingual — *only* when two **distinct** languages appear across the
   **two lines** of a cue (majority pattern). Two languages inside one line does **not** count;
   a monolingual caption wrapped onto 2 lines does **not** count (both lines same lang).
2. Let the user pick **which line is the source** to translate from.
3. Translate the chosen source → user-chosen new targets (billed as usual).
4. **Do not discard the other pre-existing language.** Carry it through: show it in the
   review screen alongside source + new translations, and merge it into the stacked download.
   It is **not billed** (no translation performed for it).

## Key existing seams (reuse these)

- Cue model: `pkg-srt-services/.../api.py:37` — one cue = `{index,start,end,text}`, multi-line
  text is `\n`-joined in `text` (`_parse_block:99`).
- Whole pipeline reads `input.srt`: translation input `orchestration.py:355-357`, landing
  re-parse `:396`. So **making `input.srt` source-only** is enough to make translation +
  `source_minutes` correct with zero downstream changes.
- Stacked/per-lang download (`routes.py:204` `download_job`) already reads one stored
  `output.<lang>.srt` per language and unions `valid = {source_lang, *targets}`
  (`routes.py:~245`). A carried language just needs its own `output.<lang>.srt` +
  membership in the `valid` set → download machinery works unchanged.
- Billing counts only `tgt_langs` (`credits.py:89` `debit_job_once`). Keep carried lang
  **out of `tgt_langs`** and it is automatically unbilled.
- Stacked assembly: `build_stacked_srt` (`api.py:164`) already stacks arbitrary langs in a
  given order — reused as-is.

## Design

Model a bilingual upload as: **source_lang** (translated, billed) + **one carried language**
(pre-supplied, stored as an output, unbilled). Split happens at enqueue; `input.srt` becomes
source-only so everything downstream stays monolingual.

**Server derives the languages — the client is not trusted for them** (review comment L81).
The client sends only which line the user picked (`source_line`). At job creation the backend
**re-runs bilingual detection on the request cues** (deterministic: same cues → same result) and
derives `source_lang = line_langs[source_line]` and `carried_lang = line_langs[other line]`.
Client-supplied language codes for the bilingual path are ignored.

**Package boundary — detection is injected, not imported** (review comment L94). `pkg-job-orch`
is independently installable and depends only on `pkg-srt-services`; it must **not** import the
host app `srt_backend` or Lingua. So the Lingua-backed detector lives in the host app and is
**injected through `JobContext`**, mirroring the existing `worker_client` seam
(`orchestration.py:152`, wired in `srt_backend/app.py:_build_ctx()` `:80`).

## Backend changes

1. **Shared result type + detector Protocol** — `pkg-srt-services/.../api.py` (pure, no Lingua)
   - Add `@dataclass(frozen=True) BilingualDetection(is_bilingual: bool, line_langs: list[str],
     confidence: float)` and a type alias `BilingualDetector = Callable[[list[Cue]],
     BilingualDetection]`. Add both to `__all__`. This lets `pkg-job-orch` reference the type
     without depending on the host app or Lingua.

2. **Detection impl** — `srt-backend/src/srt_backend/detection.py` (Lingua stays here)
   - Factor the per-sample lingua+zh logic out of `detect()` into a helper
     `_detect_code(sample: str) -> str | None` (reuse in both paths).
   - Add `detect_bilingual(cues) -> BilingualDetection` (imports the dataclass from
     `pkg_srt_services.api`):
     - **Per-cue ordered pair, not per-position aggregation** (review comment L62): for each cue
       whose `text.split("\n")` has **exactly 2** lines, detect each line's code with
       `_detect_code` → ordered pair `(langA, langB)`. Only keep pairs where both are supported
       and `langA != langB`.
     - Tally the distinct ordered pairs. `is_bilingual` iff a **single** distinct pair is the
       **majority of *all* cues** in the file (not just of 2-line cues) — i.e.
       `count(winning_pair) / len(cues) > 0.5`, subject to a small `min_cues` floor. This
       enforces the user's rule: a file counts as bilingual only when *most* lines carry the
       same two-language pattern; a handful of stray 2-language cues does **not** qualify.
     - False positives handled naturally: a wrapped monolingual caption → `langA == langB` →
       pair discarded; mixed/irregular files → no single pair reaches majority → not bilingual.
     - `line_langs = [winningLangA, winningLangB]` (line-position order of the winning pair);
       `confidence` = winning-pair share.

3. **`/srt/prepare`** — `srt-backend/src/srt_backend/routes_srt.py:149`
   - Call `detect_bilingual(cues)`; add `bilingual: {line_langs:[...]} | null` to the response
     (null when not bilingual). Keep returning `detected_lang` unchanged.

4. **Pure split helper** — `pkg-srt-services/.../api.py`
   - `split_bilingual(cues, source_line: int) -> tuple[list[Cue], list[Cue]]` returning
     `(source_cues, carried_cues)`: for each 2-line cue, `source_cues` text = line[source_line],
     `carried_cues` text = the other line; cues without 2 lines → kept whole in `source_cues`,
     omitted from `carried_cues`. Add to `__all__`. Unit-testable, no I/O.

5. **Inject the detector via `JobContext`** — `pkg-job-orch/.../orchestration.py:137` + host wiring
   - Add field `bilingual_detector: BilingualDetector | None = None` to `JobContext` (imported
     from `pkg_srt_services.api`), same optional-with-default shape as `worker_client`.
   - Host app wires it in `srt_backend/app.py:_build_ctx()` (`:80`):
     `bilingual_detector=detect_bilingual`. Keeps Lingua out of `pkg-job-orch`.
   - Tests can inject a fake detector (no Lingua needed in `pkg-job-orch` tests).

6. **`CreateJobRequest` + `create_job`** — `pkg-job-orch/.../routes.py:37`, handler `:60`
   - Add optional `source_line: int | None` (validator: 0 or 1). **Do not** add a client
     `carried_lang` — it is derived server-side.
   - **Make `source_lang` optional with mode validation** (review comment L129): change
     `source_lang: str = Field(min_length=1)` → `source_lang: str | None`, plus a model
     validator — **required (non-empty) when `source_line is None`; ignored/derived when
     `source_line` is present**. This keeps the monolingual path unchanged while allowing
     bilingual requests to omit it.
   - In `create_job`, when `source_line` is set: `det = ctx.bilingual_detector(cues)`
     (injected; not an import of `srt_backend`).
     - If `ctx.bilingual_detector is None` or `not det.is_bilingual` → 400
       ("file is not bilingual").
     - Else derive `source_lang = det.line_langs[source_line]`,
       `carried_lang = det.line_langs[1 - source_line]`.
   - **Reject overlap after target normalization** (review comment L80): compute
     `clean = clean_target_langs(body.targets, source_lang)`; if `carried_lang in clean` → 400
     ("carried language cannot also be a translation target"). This prevents the worker
     overwriting `output.<carried_lang>.srt` and billing it. `clean` (carried excluded) is what
     feeds the billing pre-check and `enqueue`.

7. **`enqueue`** — `pkg-job-orch/.../orchestration.py:182`
   - Accept `carried_lang` + `source_line` (derived by the route). If set:
     `source_cues, carried_cues = split_bilingual(cues, source_line)`.
     Store `input.srt = serialize(source_cues)` (source-only → translation & `source_minutes`
     correct). Write `output.<carried_lang>.srt = serialize(carried_cues)` immediately.
     Persist new `Job.carried_langs`.
   - `clean_target_langs` / billing untouched → carried lang not billed (and cannot collide with
     a target — rejected in the route).

8. **Job model + migration** — `pkg-job-orch/.../models.py:149`
   - Add `carried_langs: str = Field(default="")` (CSV; reuse `tgt_langs_to_csv/from_csv`
     pattern). Expose in `to_dict` / status payload (`carried_langs: list[str]`).
   - Add a migration under `pkg-job-orch/.../migrations/`.

9. **Download** — `pkg-job-orch/.../routes.py` `download_job`
   - Per-lang guard (`routes.py:229`, `if langs is None and lang not in targets`) currently 404s
     the carried lang (review comment L95). Fix: build `downloadable = {*targets, *carried_langs}`
     and guard on `lang not in downloadable` so a direct `?lang=<carried>` download resolves to
     its stored `output.<lang>.srt`.
   - Stacked guard: `valid = {source_lang, *targets, *carried_langs}` (`routes.py:242`).
   - Include carried lang in `stacked.default_order` (order: source, carried, then targets).

## Frontend changes (`srt-frontend/src`)

1. **`api.ts`**: `PrepareResponse` += `bilingual: { line_langs: string[] } | null`.
   `createJob` params += `sourceLine?` → send `source_line` only (backend derives
   `source_lang` + `carried_lang`; client does not send language codes for the bilingual path).
   `JobStatusResponse` += `carried_langs?: string[]`.
2. **`App.tsx` `parseEntry` (~:171)**: store `prepare.bilingual` on the entry; when bilingual,
   do **not** auto-fill `sourceLang` from `detected_lang` — the user picks via the line chooser.
3. **`ConfigureScreen.tsx`**: when `entry.bilingual`, render "This file already contains 2
   languages" + a radio to choose which line is the source (labels from `line_langs`). Choice
   sets `sourceLine` (and `sourceLang` locally for display = `line_langs[sourceLine]`). Exclude
   the other line's language (`line_langs[1 - sourceLine]`) from selectable targets — the backend
   also rejects the overlap. Note: carried language is kept and not charged.
4. **`sourceMetrics.ts`**: billing preview uses the count of **new targets only** (carried
   excluded) — already correct as long as carried isn't added to targets.
5. **Review + `StackedOutput.tsx` / `stackedPreview.ts`**: include the carried lang in the
   language set shown and in the stacked merge/download order (source, carried, targets).

## Verification

- Backend unit (`srt-backend/tests`):
  - `detect_bilingual` on `test_files/1960-eleves-cours-francais.srt` → `is_bilingual`,
    `line_langs == ["fr","zh"]`.
  - **Majority rule**: a fixture where only a *few* cues are 2-language but most are
    monolingual → **not** bilingual (no single pair reaches >50% of all cues).
  - A monolingual wrapped-caption fixture and a single-line fixture → **not** bilingual.
  - `split_bilingual` roundtrip.
  - Job creation `source_line`: backend re-detects, `input.srt` is source-only,
    `output.<carried>.srt` exists, `carried_langs` persisted; billing (`test_pricing_plan.py`
    style) = new-target count only (carried excluded).
  - **Overlap rejected**: `source_line` set with the carried lang also in `targets` → 400.
  - Not-bilingual + `source_line` set → 400.
  - Monolingual path unchanged: `source_lang` given, no `source_line` → works; missing both → 400.
  - `pkg-job-orch` tests inject a **fake `bilingual_detector`** (no Lingua dependency in that
    package's test suite), proving the injection seam.
  - **Direct carried download**: `?lang=<carried>` returns its stored SRT (not 404).
  - `download_job` stacked with `langs=fr,zh,en` returns source+carried+target lines in order.
- Frontend: parse the reference fixture → line chooser appears; submitting sends `source_line`
  only; review lists all 3 langs; stacked download merges them.
- End-to-end via `/verify`: upload `test_files/1960-eleves-cours-francais.srt`, pick French as
  source, add English target, confirm review shows fr+zh+en and the stacked download merges all.
