"""되새김질 흰 십자 (0.2.65 ship · design/57; 앱 버전은 후속 범프)."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from sentence_reading.api.app import app

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "src" / "sentence_reading" / "static"
APP_JS = STATIC / "app.js"
CSS = STATIC / "styles.css"
INDEX = STATIC / "index.html"
DESIGN = ROOT / "docs" / "design" / "57-section-review-crosshair.md"

WHITE_CROSS_SVG = "stroke='%23ffffff'"


def test_status_section_review_crosshair() -> None:
    st = TestClient(app).get("/api/status").json()
    assert st["version"] == "0.3.156"
    assert st["section_review_crosshair"] is True
    assert st["section_review_keys"] is True
    assert "live_enable" not in st
    assert "ips" not in st


def test_css_white_crosshair_wiring() -> None:
    css = CSS.read_text(encoding="utf-8")
    assert "design/57" in css
    assert "body.is-section-review .section-review-sheet" in css
    assert WHITE_CROSS_SVG in css
    assert "is-browser-fullscreen.is-section-review" in css
    assert ".section-review-flow-seg.is-flow-focus::before" in css
    assert "section-review-flow-edit" in css
    # buttons keep pointer
    assert "section-review-sheet button" in css
    html = INDEX.read_text(encoding="utf-8")
    assert "흰 십자" in html
    app_js = APP_JS.read_text(encoding="utf-8")
    assert "design/57" in app_js or "흰 십자" in app_js
    assert "is-section-review" in app_js


def test_edge_empty_and_architecture() -> None:
    """표시만 — advance/index 변경 없음 · 빈 flow 에도 시트 커서 규칙은 유지."""
    css = CSS.read_text(encoding="utf-8")
    assert "pointer-events: none" in css  # focus marker
    app_js = APP_JS.read_text(encoding="utf-8")
    # open/close still toggle body class (cursor gate)
    assert 'classList.add("is-section-review")' in app_js
    assert 'classList.remove("is-section-review")' in app_js
    # no new index mutation helpers for crosshair
    assert "section_review_crosshair" not in app_js  # flag is server status only


def test_design_and_assets() -> None:
    design = DESIGN.read_text(encoding="utf-8")
    assert "0.2.65" in design
    assert "Trading Gate" in design or "ASR 밖" in design
    served = TestClient(app).get("/").text
    assert "app.js?v=0.3.156" in served
    assert "styles.css?v=0.3.156" in served
