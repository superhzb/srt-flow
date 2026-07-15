#!/usr/bin/env python3
"""Drive the language fixtures through a live worker's /translate endpoint.

Feeds each supported-source-language fixture in ``test_files/matrix/languages/``
to a running worker, requesting several targets per source, then validates the
response shape (ids preserved, every requested target present + non-empty) and
writes a rich Markdown debug report.

Usage:
    python scripts/drive_translation.py \
        --base-url http://127.0.0.1:19405 --label cloud \
        --report /path/report.md [--targets-per 3] [--files en,fr] \
        [--worker-log /path/uvicorn.log] [--timeout 300]
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent.parent
LANG_DIR = ROOT / "test_files" / "matrix" / "languages"
sys.path.insert(0, str(ROOT / "srt-backend" / "pkg-srt-services" / "src"))
from pkg_srt_services.api import parse  # noqa: E402

# languages.yaml source langs the workers can load (ar/mixed excluded on purpose).
SUPPORTED = ["en", "es", "zh", "zh-TW", "fr", "de", "pt", "ja", "ko"]
# Target preference order; per source we take the first N that aren't the source.
TARGET_PRIORITY = ["en", "zh", "es", "ja", "fr", "de", "ko", "pt", "zh-TW"]


def targets_for(source: str, n: int) -> list[str]:
    picks = [t for t in TARGET_PRIORITY if t != source]
    return picks[:n]


def segments_from(path: Path, source: str) -> list[dict[str, object]]:
    cues = parse(path.read_bytes().decode("utf-8"))
    return [{"id": c.index, source: c.text} for c in cues]


def post_json(url: str, payload: dict[str, object], timeout: float) -> tuple[int, str]:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = Request(url, data=data, headers={"content-type": "application/json"}, method="POST")
    try:
        with urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read().decode("utf-8")
    except HTTPError as exc:
        return exc.code, exc.read().decode("utf-8")


def get(url: str, timeout: float) -> tuple[int, str]:
    with urlopen(url, timeout=timeout) as resp:
        return resp.status, resp.read().decode("utf-8")


def validate(
    source: str, targets: list[str], segments: list[dict[str, object]], body: str
) -> tuple[bool, list[str]]:
    problems: list[str] = []
    try:
        resp = json.loads(body)
    except json.JSONDecodeError as exc:
        return False, [f"response is not JSON: {exc}"]
    if resp.get("source_lang") != source:
        problems.append(f"source_lang mismatch: {resp.get('source_lang')!r} != {source!r}")
    if resp.get("targets") != targets:
        problems.append(f"targets mismatch: {resp.get('targets')!r} != {targets!r}")
    out = resp.get("segments")
    if not isinstance(out, list) or len(out) != len(segments):
        problems.append(
            f"segment count: got {len(out) if isinstance(out, list) else 'n/a'}, "
            f"want {len(segments)}"
        )
        return not problems, problems
    for want, got in zip(segments, out, strict=False):
        if got.get("id") != want["id"]:
            problems.append(f"id mismatch: {got.get('id')} != {want['id']}")
        if got.get(source) != want[source]:
            problems.append(f"source text not echoed for id={want['id']}")
        for t in targets:
            val = got.get(t)
            if not isinstance(val, str) or not val.strip():
                problems.append(f"id={want['id']} target={t}: missing/empty translation ({val!r})")
    return not problems, problems


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", required=True)
    ap.add_argument("--label", required=True)
    ap.add_argument("--report", required=True)
    ap.add_argument("--targets-per", type=int, default=3)
    ap.add_argument("--files", default="", help="comma-separated stems; default = all supported")
    ap.add_argument("--worker-log", default="")
    ap.add_argument("--timeout", type=float, default=300.0)
    args = ap.parse_args()

    if args.files.strip():
        stems = [s.strip() for s in args.files.split(",") if s.strip()]
    else:
        stems = SUPPORTED
    stems = [s for s in stems if s in SUPPORTED]

    lines: list[str] = [
        f"# translation drive report — worker: {args.label}",
        "",
        f"- base_url: `{args.base_url}`",
        f"- targets_per_source: {args.targets_per}",
        f"- sources: `{stems}`",
    ]

    # Health first — captures a fast failure with context.
    try:
        hs, hb = get(f"{args.base_url}/health", timeout=10)
        lines.append(f"- health: `{hs}` `{hb.strip()}`")
    except (HTTPError, URLError, TimeoutError) as exc:
        lines.append(f"- health: **UNREACHABLE** {type(exc).__name__}: {exc}")
        _write(args.report, lines, args.worker_log)
        print(f"[{args.label}] worker unreachable: {exc}")
        return 2

    passed = failed = 0
    for stem in stems:
        path = LANG_DIR / f"{stem}.srt"
        if not path.exists():
            continue
        source = stem
        targets = targets_for(source, args.targets_per)
        segments = segments_from(path, source)
        payload = {"source_lang": source, "targets": targets, "segments": segments}

        lines += ["", f"## {stem}.srt  ({source} -> {targets})", ""]
        t0 = time.perf_counter()
        try:
            status_code, body = post_json(f"{args.base_url}/translate", payload, args.timeout)
        except (URLError, TimeoutError) as exc:
            failed += 1
            lines += [f"- **REQUEST FAILED** {type(exc).__name__}: {exc}"]
            print(f"[{args.label}] {stem}: request failed: {exc}")
            continue
        secs = round(time.perf_counter() - t0, 2)

        ok = status_code == 200
        problems: list[str] = []
        if ok:
            ok, problems = validate(source, targets, segments, body)
        else:
            problems = [f"HTTP {status_code}"]

        verdict = "PASS" if ok else "FAIL"
        (passed, failed) = (passed + 1, failed) if ok else (passed, failed + 1)
        lines += [
            f"- verdict: **{verdict}**",
            f"- http_status: {status_code}",
            f"- request_seconds: {secs}",
            f"- segment_count: {len(segments)}",
        ]
        if problems:
            lines += ["- problems:"] + [f"    - {p}" for p in problems]
        pretty = body
        try:
            pretty = json.dumps(json.loads(body), ensure_ascii=False, indent=2)
        except json.JSONDecodeError:
            pass
        lines += [
            "",
            "<details><summary>raw response</summary>",
            "",
            "```json",
            pretty,
            "```",
            "",
            "</details>",
        ]
        print(
            f"[{args.label}] {stem}: {verdict} ({secs}s, http {status_code})"
            + (f" — {problems[0]}" if problems else "")
        )

    lines[0] += f"  —  {passed} passed / {failed} failed"
    _write(args.report, lines, args.worker_log)
    print(f"[{args.label}] TOTAL {passed} passed / {failed} failed -> {args.report}")
    return 0 if failed == 0 else 1


def _write(report: str, lines: list[str], worker_log: str) -> None:
    out = list(lines)
    if worker_log and Path(worker_log).exists():
        log = Path(worker_log).read_text(encoding="utf-8", errors="replace")
        tail = "\n".join(log.splitlines()[-120:])
        out += ["", "## Worker Log (tail)", "", "```text", tail, "```"]
    Path(report).parent.mkdir(parents=True, exist_ok=True)
    Path(report).write_text("\n".join(out) + "\n", encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
