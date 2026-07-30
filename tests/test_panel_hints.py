"""패널 단축키 안내 줄 기본 숨김 (0.2.74 · design/60)."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from sentence_reading.api.app import app

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "src" / "sentence_reading" / "static"
APP_JS = STATIC / "app.js"
CSS = STATIC / "styles.css"
INDEX = STATIC / "index.html"
DESIGN = ROOT / "docs" / "design" / "60-panel-hints.md"


def test_status_panel_hints_optional() -> None:
    st = TestClient(app).get("/api/status").json()
    assert st["version"] == "0.2.74"
    assert st["panel_hints_optional"] is True
    assert st["guide_header"] is True
    assert "live_enable" not in st
    assert "ips" not in st


def test_html_hints_hidden_by_default() -> None:
    html = INDEX.read_text(encoding="utf-8")
    assert 'id="sentenceHint"' in html
    assert 'id="figureHint"' in html
    assert "panel-chrome-hint" in html
    assert 'id="guideShowHintsCheck"' in html
    assert "화면에도 단축키 안내 줄 보이기" in html
    # both panel hints start hidden in markup
    for hid in ("sentenceHint", "figureHint"):
        i = html.find(f'id="{hid}"')
        assert i > 0
        # attribute near the id
        chunk = html[max(0, i - 80) : i + 40]
        assert "hidden" in chunk
    # contextual hints kept (not panel chrome)
    assert "note-hint" in html
    assert "section-review-hint" in html


def test_js_css_wiring() -> None:
    src = APP_JS.read_text(encoding="utf-8")
    assert "design/60" in src
    assert "showPanelHints" in src
    assert "applyPanelHints" in src
    assert "guideShowHintsCheck" in src
    css = CSS.read_text(encoding="utf-8")
    assert "design/60" in css
    assert ".panel-chrome-hint[hidden]" in css


def test_edge_legacy_pref_and_missing_nodes() -> None:
    src = APP_JS.read_text(encoding="utf-8")
    # legacy boolean / missing showPanelHints → false
    assert "showPanelHints = false" in src or "showPanelHints: false" in src
    assert 'typeof data === "boolean"' in src
    # missing DOM no-op
    assert "if (el.sentenceHint)" in src
    assert "if (el.figureHint)" in src
    # only panel chrome ids — note/section-review overlays untouched
    assert "getElementById(\"sentenceHint\")" in src
    assert "getElementById(\"figureHint\")" in src
    assert "getElementById(\"noteHint\")" not in src
    design = DESIGN.read_text(encoding="utf-8")
    assert "0.2.74" in design
    assert "Trading Gate" in design or "ASR 밖" in design
    served = TestClient(app).get("/").text
    assert "app.js?v=0.2.74" in served
    assert "styles.css?v=0.2.74" in served
    assert "sentenceHint" in served
