#!/usr/bin/env python3
"""Generate a matrix of SRT test fixtures for the translation feature.

Covers three buckets under ``test_files/matrix/``:

* ``languages/``  — valid SRT in each supported source language (plus RTL and
  a mixed-language file) to exercise detection + translation.
* ``edge-cases/`` — valid SRT that stresses the parser (BOM, CRLF, dot-decimal
  timestamps, HTML tags, non-sequential indices, emoji, ...). All must parse.
* ``invalid/``    — malformed payloads that MUST be rejected (empty text,
  bad timestamps, non-UTF8 bytes, ...). Negative tests.

Re-run any time: ``python scripts/gen_test_srt.py``. Idempotent.
"""

from __future__ import annotations

import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "test_files" / "matrix"


def cue(idx: int, start: str, end: str, text: str) -> str:
    return f"{idx}\n{start} --> {end}\n{text}"


def srt(*cues: str, sep: str = "\n\n", trailing: str = "\n") -> str:
    return sep.join(cues) + trailing


# --------------------------------------------------------------------------
# languages/ — valid, normal SRT, real-ish captions in each source language.
# --------------------------------------------------------------------------
LANGUAGES: dict[str, str] = {
    "en.srt": srt(
        cue(1, "00:00:01,000", "00:00:03,500", "Good morning. Thanks for coming in today."),
        cue(
            2, "00:00:03,600", "00:00:06,200", "I wanted to walk you through how the process works."
        ),
        cue(
            3,
            "00:00:06,300",
            "00:00:09,000",
            "It takes real strength to make it all the way to the end.",
        ),
        cue(4, "00:00:09,100", "00:00:11,800", "But you won't be doing it alone."),
        cue(5, "00:00:11,900", "00:00:14,400", "We'll be with you every step of the way."),
    ),
    "es.srt": srt(
        cue(1, "00:00:01,000", "00:00:03,500", "Buenos días. Gracias por venir hoy."),
        cue(2, "00:00:03,600", "00:00:06,200", "Quería explicarte cómo funciona el proceso."),
        cue(
            3, "00:00:06,300", "00:00:09,000", "Hace falta mucha fuerza para llegar hasta el final."
        ),
        cue(4, "00:00:09,100", "00:00:11,800", "Pero no lo harás solo."),
        cue(5, "00:00:11,900", "00:00:14,400", "Estaremos contigo en cada paso del camino."),
    ),
    "de.srt": srt(
        cue(
            1, "00:00:01,000", "00:00:03,500", "Guten Morgen. Danke, dass Sie heute gekommen sind."
        ),
        cue(
            2,
            "00:00:03,600",
            "00:00:06,200",
            "Ich wollte Ihnen erklären, wie der Ablauf funktioniert.",
        ),
        cue(
            3,
            "00:00:06,300",
            "00:00:09,000",
            "Man braucht wirklich viel Stärke, um es bis zum Ende zu schaffen.",
        ),
        cue(4, "00:00:09,100", "00:00:11,800", "Aber Sie müssen das nicht allein tun."),
        cue(5, "00:00:11,900", "00:00:14,400", "Wir begleiten Sie bei jedem Schritt."),
    ),
    "pt.srt": srt(
        cue(1, "00:00:01,000", "00:00:03,500", "Bom dia. Obrigado por vir hoje."),
        cue(2, "00:00:03,600", "00:00:06,200", "Eu queria explicar como o processo funciona."),
        cue(3, "00:00:06,300", "00:00:09,000", "É preciso muita força para chegar até o fim."),
        cue(4, "00:00:09,100", "00:00:11,800", "Mas você não vai fazer isso sozinho."),
        cue(5, "00:00:11,900", "00:00:14,400", "Estaremos com você em cada passo do caminho."),
    ),
    "fr.srt": srt(
        cue(1, "00:00:01,000", "00:00:03,500", "Bonjour. Merci d'être venu aujourd'hui."),
        cue(
            2,
            "00:00:03,600",
            "00:00:06,200",
            "Je voulais vous expliquer comment se déroule le processus.",
        ),
        cue(
            3,
            "00:00:06,300",
            "00:00:09,000",
            "Et il faut être vraiment fort pour aller jusqu'au bout.",
        ),
        cue(4, "00:00:09,100", "00:00:11,800", "Mais vous ne serez pas seul."),
        cue(5, "00:00:11,900", "00:00:14,400", "Nous serons avec vous à chaque étape."),
    ),
    "zh.srt": srt(
        cue(1, "00:00:01,000", "00:00:03,500", "早上好，感谢你今天过来。"),
        cue(2, "00:00:03,600", "00:00:06,200", "我想跟你说明一下整个流程是怎么运作的。"),
        cue(3, "00:00:06,300", "00:00:09,000", "而且要走到最后，真的需要很强的意志。"),
        cue(4, "00:00:09,100", "00:00:11,800", "但你不会一个人面对。"),
        cue(5, "00:00:11,900", "00:00:14,400", "我们会陪着你走过每一步。"),
    ),
    "zh-TW.srt": srt(
        cue(1, "00:00:01,000", "00:00:03,500", "早安，謝謝你今天過來。"),
        cue(2, "00:00:03,600", "00:00:06,200", "我想跟你說明一下整個流程是怎麼運作的。"),
        cue(3, "00:00:06,300", "00:00:09,000", "而且要走到最後，真的需要很強的意志。"),
        cue(4, "00:00:09,100", "00:00:11,800", "但你不會一個人面對。"),
        cue(5, "00:00:11,900", "00:00:14,400", "我們會陪著你走過每一步。"),
    ),
    "ja.srt": srt(
        cue(1, "00:00:01,000", "00:00:03,500", "おはようございます。今日は来てくれてありがとう。"),
        cue(2, "00:00:03,600", "00:00:06,200", "この流れがどう進むのか説明したかったんです。"),
        cue(3, "00:00:06,300", "00:00:09,000", "最後までやり抜くには、本当に強さが必要です。"),
        cue(4, "00:00:09,100", "00:00:11,800", "でも、一人でやるわけではありません。"),
        cue(5, "00:00:11,900", "00:00:14,400", "一歩ずつ、そばで支えます。"),
    ),
    "ko.srt": srt(
        cue(1, "00:00:01,000", "00:00:03,500", "안녕하세요. 오늘 와 주셔서 감사합니다."),
        cue(2, "00:00:03,600", "00:00:06,200", "이 과정이 어떻게 진행되는지 설명하고 싶었어요."),
        cue(3, "00:00:06,300", "00:00:09,000", "끝까지 해내려면 정말 강해야 합니다."),
        cue(4, "00:00:09,100", "00:00:11,800", "하지만 혼자 하는 게 아니에요."),
        cue(5, "00:00:11,900", "00:00:14,400", "한 걸음 한 걸음 함께하겠습니다."),
    ),
    # RTL, not a supported target — exercises detection of an unsupported source.
    "ar.srt": srt(
        cue(1, "00:00:01,000", "00:00:03,500", "صباح الخير. شكرًا لحضورك اليوم."),
        cue(2, "00:00:03,600", "00:00:06,200", "أردت أن أشرح لك كيف تسير العملية."),
        cue(3, "00:00:06,300", "00:00:09,000", "يتطلب الأمر قوة حقيقية للوصول إلى النهاية."),
        cue(4, "00:00:09,100", "00:00:11,800", "لكنك لن تفعل ذلك وحدك."),
        cue(5, "00:00:11,900", "00:00:14,400", "سنكون معك في كل خطوة."),
    ),
    # Multiple languages within one file — tests detection on mixed input.
    "mixed-langs.srt": srt(
        cue(1, "00:00:01,000", "00:00:03,500", "Hello, welcome to the show."),
        cue(2, "00:00:03,600", "00:00:06,200", "Bonjour et bienvenue dans l'émission."),
        cue(3, "00:00:06,300", "00:00:09,000", "こんにちは、番組へようこそ。"),
        cue(4, "00:00:09,100", "00:00:11,800", "Hola y bienvenidos al programa."),
        cue(5, "00:00:11,900", "00:00:14,400", "欢迎收看本期节目。"),
    ),
}


# --------------------------------------------------------------------------
# edge-cases/ — valid but structurally unusual. All MUST parse.
# --------------------------------------------------------------------------
EDGE_TEXT: dict[str, str] = {
    # Multi-line cue bodies (newlines preserved).
    "multiline.srt": srt(
        cue(
            1,
            "00:00:01,000",
            "00:00:04,000",
            "First line of the caption.\nSecond line of the caption.",
        ),
        cue(
            2,
            "00:00:04,100",
            "00:00:07,000",
            "- Dialogue from speaker one.\n- Reply from speaker two.",
        ),
    ),
    # Inline styling markup that must survive as text.
    "html-tags.srt": srt(
        cue(1, "00:00:01,000", "00:00:04,000", "<i>Italic emphasis here.</i>"),
        cue(
            2,
            "00:00:04,100",
            "00:00:07,000",
            '<b>Bold</b> and <font color="#ffff00">colored</font> text.',
        ),
        cue(3, "00:00:07,100", "00:00:10,000", "{\\an8}Top-positioned caption."),
    ),
    # Non-sequential / gapped indices (parser keeps them as-is).
    "nonseq-index.srt": srt(
        cue(5, "00:00:01,000", "00:00:03,000", "Starts at five."),
        cue(10, "00:00:03,100", "00:00:05,000", "Jumps to ten."),
        cue(11, "00:00:05,100", "00:00:07,000", "Then eleven."),
    ),
    # Single cue only.
    "single-cue.srt": srt(
        cue(1, "00:00:00,500", "00:00:02,500", "The only cue in this file."),
    ),
    # Emoji and assorted special characters.
    "emoji-special.srt": srt(
        cue(1, "00:00:01,000", "00:00:03,000", "Great job! 🎉👏 Let's keep going ➡️"),
        cue(2, "00:00:03,100", "00:00:05,000", "Symbols: © ® ™ € £ ¥ — “curly” ‘quotes’ …"),
        cue(3, "00:00:05,100", "00:00:07,000", "Math: ½ + ¼ = ¾, x² ≤ y, α β γ"),
    ),
    # Long single-cue body.
    "long-cue.srt": srt(
        cue(
            1,
            "00:00:01,000",
            "00:00:12,000",
            "This is a deliberately long caption used to check how the pipeline handles "
            "a single cue that carries a great deal of text, well beyond what a reader "
            "could comfortably absorb in the allotted window, spanning many words in a "
            "row without any line breaks at all to force wrapping and batching behavior.",
        ),
    ),
    # 1-digit hour field (allowed by the timestamp regex).
    "one-digit-hour.srt": srt(
        cue(1, "0:00:01,000", "0:00:03,000", "Timestamp uses a single-digit hour."),
        cue(2, "0:00:03,100", "0:00:05,000", "Still valid per the parser."),
    ),
    # Leading/trailing whitespace around index and inside blocks.
    "trailing-ws.srt": srt(
        cue(1, "00:00:01,000", "00:00:03,000", "Body has trailing spaces.   "),
        cue(2, "00:00:03,100", "00:00:05,000", "   Body has leading spaces."),
    ),
    # Body is only punctuation (valid: non-empty after strip).
    "punctuation-only.srt": srt(
        cue(1, "00:00:01,000", "00:00:03,000", "..."),
        cue(2, "00:00:03,100", "00:00:05,000", "?!"),
        cue(3, "00:00:05,100", "00:00:07,000", "—"),
        cue(4, "00:00:07,100", "00:00:09,000", "。！？、「」"),
    ),
    # Body is only signs / non-letter glyphs (music notes, brackets, chevrons).
    "symbols-only.srt": srt(
        cue(1, "00:00:01,000", "00:00:03,000", "♪"),
        cue(2, "00:00:03,100", "00:00:05,000", "♪ ♪ ♪"),
        cue(3, "00:00:05,100", "00:00:07,000", "[MUSIC]"),
        cue(4, "00:00:07,100", "00:00:09,000", ">>"),
        cue(5, "00:00:09,100", "00:00:11,000", "***"),
    ),
    # A single physical line with no spaces/breaks — stresses no-wrap handling.
    "very-long-line.srt": srt(
        cue(
            1,
            "00:00:01,000",
            "00:00:12,000",
            "VeryLongUnbrokenTokenNoSpaces" * 60,
        ),
    ),
    # Body is only digits — must not be mistaken for an index line.
    "numeric-body.srt": srt(
        cue(1, "00:00:01,000", "00:00:03,000", "1234567890"),
        cue(2, "00:00:03,100", "00:00:05,000", "007"),
        cue(3, "00:00:05,100", "00:00:07,000", "42\n99"),
    ),
    # One cue with many stacked lines (all preserved).
    "many-lines.srt": srt(
        cue(
            1,
            "00:00:01,000",
            "00:00:08,000",
            "\n".join(f"Line {n} of a tall caption." for n in range(1, 9)),
        ),
    ),
    # Extra blank lines between blocks (split on 1+ blank lines).
    "extra-blank-lines.srt": srt(
        cue(1, "00:00:01,000", "00:00:03,000", "First block."),
        cue(2, "00:00:03,100", "00:00:05,000", "Second block after several blank lines."),
        sep="\n\n\n\n",
    ),
}
# Files that must be emitted with non-default bytes (BOM / CRLF / dot decimal).
EDGE_RAW: dict[str, bytes] = {}

_bom_body = srt(
    cue(1, "00:00:01,000", "00:00:03,000", "This file begins with a UTF-8 BOM."),
    cue(2, "00:00:03,100", "00:00:05,000", "The parser must tolerate it."),
)
EDGE_RAW["bom.srt"] = b"\xef\xbb\xbf" + _bom_body.encode("utf-8")

_crlf_body = srt(
    cue(1, "00:00:01,000", "00:00:03,000", "Windows line endings (CRLF)."),
    cue(2, "00:00:03,100", "00:00:05,000", "Normalized to LF on parse."),
)
EDGE_RAW["crlf.srt"] = _crlf_body.replace("\n", "\r\n").encode("utf-8")

_dot_body = srt(
    cue(1, "00:00:01.000", "00:00:03.000", "Timestamps use a dot decimal separator."),
    cue(2, "00:00:03.100", "00:00:05.000", "Canonicalized to comma on serialize."),
)
EDGE_RAW["dot-decimal.srt"] = _dot_body.encode("utf-8")


# --------------------------------------------------------------------------
# invalid/ — MUST be rejected. Negative tests for the 400 paths.
# --------------------------------------------------------------------------
INVALID_TEXT: dict[str, str] = {
    # Whitespace-only payload -> "empty SRT payload".
    "whitespace-only.srt": "   \n\n  \t\n",
    # Cue with a blank text body -> "cue N has empty text".
    "empty-text-cue.srt": "1\n00:00:01,000 --> 00:00:03,000\n\n",
    # Malformed timespan line.
    "bad-timestamp.srt": "1\n00:00:01 --> 00:00:03\nMissing milliseconds.\n",
    # Missing index line (first line is not digits).
    "missing-index.srt": "not-a-number\n00:00:01,000 --> 00:00:03,000\nText here.\n",
    # Block too short (index + text, no timespan).
    "no-timespan.srt": "1\nJust text, no timing line.\n",
    # Arrow but reversed/garbage separator.
    "bad-arrow.srt": "1\n00:00:01,000 => 00:00:03,000\nWrong arrow token.\n",
    # Blank line inside a cue body splits the block (parser splits on \n\s*\n),
    # leaving a trailing block whose first line is not a valid index.
    "blank-line-in-body.srt": (
        "1\n00:00:01,000 --> 00:00:03,000\nFirst line of caption.\n\nStray second line.\n"
    ),
}
INVALID_RAW: dict[str, bytes] = {
    # Zero-byte file -> rejected as empty upload before parse.
    "empty.srt": b"",
    # Invalid UTF-8 (Latin-1 encoded accents) -> "file is not valid UTF-8".
    "not-utf8.srt": "1\n00:00:01,000 --> 00:00:03,000\nRésumé café déjà.\n".encode("latin-1"),
}


def write_text(path: pathlib.Path, content: str) -> None:
    path.write_bytes(content.encode("utf-8"))


def main() -> None:
    buckets: list[tuple[str, dict[str, str], dict[str, bytes]]] = [
        ("languages", LANGUAGES, {}),
        ("edge-cases", EDGE_TEXT, EDGE_RAW),
        ("invalid", INVALID_TEXT, INVALID_RAW),
    ]
    count = 0
    for name, text_files, raw_files in buckets:
        d = OUT / name
        d.mkdir(parents=True, exist_ok=True)
        for fname, content in text_files.items():
            write_text(d / fname, content)
            count += 1
        for fname, raw in raw_files.items():
            (d / fname).write_bytes(raw)
            count += 1
    print(f"wrote {count} fixtures under {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
