"""Contract tests for the committed SRT fixture matrix.

Walks ``test_files/matrix/`` and asserts each bucket behaves as designed
against the *real* parse + upload-decode rules:

* ``languages/`` and ``edge-cases/`` — must decode + parse into >=1 cue and
  round-trip through ``serialize``.
* ``invalid/`` — must be rejected, either at the upload-decode layer
  (empty bytes / non-UTF8, mirroring ``routes_srt._decode_srt``) or at parse
  (``ParseError``).

Regenerate the fixtures with ``python scripts/gen_test_srt.py``.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from pkg_srt_services.api import ParseError, parse, serialize

_MATRIX = Path(__file__).resolve().parents[2] / "test_files" / "matrix"


class _DecodeError(Exception):
    """Upload-layer rejection (mirrors ``_decode_srt``): empty or non-UTF8."""


def _decode(path: Path) -> str:
    """Byte-level upload checks that run before ``parse``, per ``_decode_srt``."""
    raw = path.read_bytes()
    if not raw:
        raise _DecodeError("uploaded file is empty")
    try:
        return raw.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise _DecodeError("file is not valid UTF-8") from exc


def _bucket(name: str) -> list[Path]:
    return sorted((_MATRIX / name).glob("*.srt"))


def _ids(paths: list[Path]) -> list[str]:
    return [p.name for p in paths]


_VALID = _bucket("languages") + _bucket("edge-cases")
_INVALID = _bucket("invalid")


def test_matrix_present() -> None:
    """Guard against a missing/unregenerated fixture tree."""
    assert _bucket("languages"), "no language fixtures — run scripts/gen_test_srt.py"
    assert _bucket("edge-cases"), "no edge-case fixtures — run scripts/gen_test_srt.py"
    assert _bucket("invalid"), "no invalid fixtures — run scripts/gen_test_srt.py"


@pytest.mark.parametrize("path", _bucket("languages") + _bucket("edge-cases"), ids=_ids(_VALID))
def test_valid_fixture_parses_and_roundtrips(path: Path) -> None:
    payload = _decode(path)
    cues = parse(payload)
    assert cues, f"{path.name}: expected at least one cue"
    # Every cue must carry non-empty text and both timestamps.
    for cue in cues:
        assert cue.text.strip(), f"{path.name}: cue {cue.index} has empty text"
        assert cue.start and cue.end
    # serialize must accept parser output (canonicalizes dot-decimal to comma).
    reserialized = serialize(cues)
    assert reserialized.endswith("\n")
    # A serialize -> parse round-trip is stable in cue count.
    assert len(parse(reserialized)) == len(cues)


@pytest.mark.parametrize("path", _bucket("invalid"), ids=_ids(_INVALID))
def test_invalid_fixture_is_rejected(path: Path) -> None:
    with pytest.raises((_DecodeError, ParseError)):
        payload = _decode(path)
        parse(payload)
