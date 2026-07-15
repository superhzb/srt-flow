# SRT test matrix

Fixtures for exercising the translation pipeline. Regenerate with
`python scripts/gen_test_srt.py` (idempotent).

Validated against the real parser (`pkg_srt_services.api.parse`) + upload
decode rules (`routes_srt._decode_srt`): everything in `languages/` and
`edge-cases/` parses; everything in `invalid/` is rejected with a 400.

## languages/ — valid, one source language each (5 cues)

| File | Source | Notes |
|------|--------|-------|
| `en.srt` | English | supported target |
| `es.srt` | Spanish | supported target |
| `de.srt` | German | supported target |
| `pt.srt` | Portuguese | supported target |
| `fr.srt` | French | supported target |
| `zh.srt` | Simplified Chinese | supported target |
| `zh-TW.srt` | Traditional Chinese | supported target |
| `ja.srt` | Japanese | supported target |
| `ko.srt` | Korean | supported target |
| `ar.srt` | Arabic (RTL) | **not** a supported target — tests unsupported-source detection |
| `mixed-langs.srt` | mixed | five languages in one file — tests detection on mixed input |

## edge-cases/ — valid but unusual; all MUST parse

| File | Stresses |
|------|----------|
| `bom.srt` | UTF-8 BOM prefix (tolerated) |
| `crlf.srt` | Windows CRLF line endings (normalized to LF) |
| `dot-decimal.srt` | `.` timestamp separator (canonicalized to `,` on serialize) |
| `multiline.srt` | multi-line cue bodies (newlines preserved) |
| `html-tags.srt` | `<i>`/`<b>`/`<font>`/`{\an8}` markup kept as text |
| `nonseq-index.srt` | non-sequential / gapped indices |
| `single-cue.srt` | one cue only |
| `emoji-special.srt` | emoji, curly quotes, symbols, math glyphs |
| `long-cue.srt` | very long single-cue body |
| `one-digit-hour.srt` | single-digit hour field (`0:00:01,000`) |
| `trailing-ws.srt` | leading/trailing whitespace in bodies |
| `extra-blank-lines.srt` | multiple blank lines between blocks |

## invalid/ — MUST be rejected (negative tests)

| File | Expected failure |
|------|------------------|
| `empty.srt` | empty upload (0 bytes) |
| `whitespace-only.srt` | `empty SRT payload` |
| `empty-text-cue.srt` | `cue N has empty text` |
| `bad-timestamp.srt` | invalid timespan (missing ms) |
| `bad-arrow.srt` | invalid timespan (`=>` not `-->`) |
| `no-timespan.srt` | block too short / missing timespan |
| `missing-index.srt` | missing/invalid index line |
| `not-utf8.srt` | `file is not valid UTF-8` (Latin-1 bytes) |

## Not covered here

`too-big` (>4 MiB) and wrong-extension are upload-layer checks, not content —
test those with any large/renamed file rather than a committed fixture.
