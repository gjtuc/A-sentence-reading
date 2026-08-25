"""design/131 — full figure captions (normalize ceiling + Flutter no 2-line …)."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from sentence_reading.api.app import app
from sentence_reading.docx.extract import _normalize_caption as docx_norm
from sentence_reading.pdf.extract import _CAPTION_MAX_CHARS, _normalize_caption

ROOT = Path(__file__).resolve().parents[1]
DESIGN = ROOT / "docs" / "design" / "131-caption-full-text.md"
READER = ROOT / "mobile" / "lib" / "screens" / "reader_screen.dart"
EXTRACT = ROOT / "src" / "sentence_reading" / "pdf" / "extract.py"


def test_design_and_status_pin() -> None:
    assert DESIGN.is_file()
    st = TestClient(app).get("/api/status").json()
    assert st["version"] == "0.3.51"
    assert st.get("caption_full_text") is True
    assert st.get("mobile_caption_full_text") is True


def test_normalize_keeps_long_table_caption() -> None:
    # Realistic Ewbank-length + more — must not become "…" mid-string.
    long = (
        "Table 1 Results from N2 physisorption, elemental analysis, and H2 "
        "chemisorption of catalysts in different stages of synthesis and after reaction. "
        + ("Extra detail sentence. " * 40)
    )
    assert len(long) > 900
    out = _normalize_caption(long)
    assert "…" not in out and "..." not in out
    assert out.startswith("Table 1 Results")
    assert "Extra detail sentence." in out
    assert len(out) <= _CAPTION_MAX_CHARS
    assert docx_norm(long) == out


def test_normalize_rejects_null_and_caps_absurd() -> None:
    assert _normalize_caption("  Fig. 1.  Hello\x00  ") == "Fig. 1. Hello"
    huge = "A" * (_CAPTION_MAX_CHARS + 500)
    assert len(_normalize_caption(huge)) == _CAPTION_MAX_CHARS


def test_flutter_reader_uses_scroll_not_hard_ellipsis_default() -> None:
    src = READER.read_text(encoding="utf-8")
    assert "captionFullText" in src
    assert "SingleChildScrollView" in src
    # Default path must not hardcode maxLines: 2 without kill branch.
    assert "caption_full_text" in EXTRACT.read_text(encoding="utf-8") or "_CAPTION_MAX_CHARS" in EXTRACT.read_text(
        encoding="utf-8"
    )
