"""한글 번역 어절 줄바꿈 (0.2.58 ship · design/50; 앱 버전은 후속 범프)."""

from __future__ import annotations

import re
from pathlib import Path

from fastapi.testclient import TestClient

from sentence_reading.api.app import app

ROOT = Path(__file__).resolve().parents[1]
CSS = ROOT / "src" / "sentence_reading" / "static" / "styles.css"


def _sentence_ko_block() -> str:
    text = CSS.read_text(encoding="utf-8")
    m = re.search(r"\.sentence-ko\s*\{([^}]+)\}", text, re.S)
    assert m, ".sentence-ko rule missing"
    return m.group(1)


def test_status_ko_word_wrap() -> None:
    st = TestClient(app).get("/api/status").json()
    assert st["version"] == "0.2.61"
    assert st["ko_word_wrap"] is True
    assert st["cite_display_clean"] is True
    assert "live_enable" not in st
    assert "ips" not in st


def test_css_keep_all_on_sentence_ko() -> None:
    block = _sentence_ko_block()
    assert "word-break: keep-all" in block
    assert "overflow-wrap: break-word" in block
    assert "line-break: strict" in block
    # must not force mid-Hangul breaks
    assert "break-all" not in block


def test_css_edge_no_break_all_override_on_ko() -> None:
    """Edge: later rules must not set break-all on .sentence-ko."""
    css = CSS.read_text(encoding="utf-8")
    # any .sentence-ko { ... break-all } would regress
    for m in re.finditer(r"\.sentence-ko[^{]*\{([^}]+)\}", css, re.S):
        assert "break-all" not in m.group(1)


def test_design_50_and_assets() -> None:
    design = (ROOT / "docs/design/50-ko-word-wrap.md").read_text(encoding="utf-8")
    assert "0.2.58" in design
    assert "keep-all" in design
    assert "Trading Gate" in design or "ASR 밖" in design
    assert "design/50" in CSS.read_text(encoding="utf-8")
    html = TestClient(app).get("/").text
    assert "styles.css?v=0.2.61" in html
    assert "app.js?v=0.2.61" in html
