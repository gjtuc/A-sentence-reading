"""Guide 헤더 배치 · nestInMore (0.2.67 ship · design/59; 앱 버전은 후속 범프)."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from sentence_reading.api.app import app

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "src" / "sentence_reading" / "static"
APP_JS = STATIC / "app.js"
CSS = STATIC / "styles.css"
INDEX = STATIC / "index.html"
DESIGN = ROOT / "docs" / "design" / "59-guide-header.md"


def test_status_guide_header() -> None:
    st = TestClient(app).get("/api/status").json()
    assert st["version"] == "0.2.79"
    assert st["guide_header"] is True
    assert st["header_overflow"] is True
    assert "live_enable" not in st
    assert "ips" not in st


def test_html_guide_outside_default() -> None:
    html = INDEX.read_text(encoding="utf-8")
    assert 'id="guideBtn"' in html
    assert "Guide" in html
    assert 'id="guideOutsideSlot"' in html
    assert 'id="guideDialog"' in html
    assert 'id="guideNestCheck"' in html
    assert "⋯ 메뉴 안에 넣기" in html or "메뉴 안에 넣기" in html
    # default: Guide in outside slot, before headerMore
    slot = html.find('id="guideOutsideSlot"')
    more = html.find('id="headerMore"')
    menu = html.find('id="headerMoreMenu"')
    assert 0 < slot < more < menu
    # guideBtn markup lives in outside slot (moved at runtime when nested)
    chunk = html[slot:more]
    assert 'id="guideBtn"' in chunk
    assert 'id="guideBtn"' not in html[menu : menu + 500]


def test_js_css_wiring() -> None:
    src = APP_JS.read_text(encoding="utf-8")
    assert "design/59" in src
    assert "guidePrefs" in src
    assert "nestInMore" in src
    assert "applyGuidePlacement" in src
    assert "loadGuidePrefs" in src
    assert "openGuideDialog" in src
    assert "asr.guide.v1" in src
    css = CSS.read_text(encoding="utf-8")
    assert "design/59" in css
    assert ".guide-outside-slot" in css
    assert ".guide-nest-label" in css


def test_edge_corrupt_pref_and_missing_dom() -> None:
    src = APP_JS.read_text(encoding="utf-8")
    # corrupt / non-object → nestInMore false
    assert "guidePrefs.nestInMore = false" in src
    assert 'typeof data === "boolean"' in src
    # missing nodes no-op
    assert "if (!el.guideBtn) return" in src
    assert "if (!el.guideDialog || typeof el.guideDialog.showModal !== \"function\")" in src
    # Esc: header more yields to guide dialog
    assert "isGuideOpen()" in src
    design = DESIGN.read_text(encoding="utf-8")
    assert "0.2.67" in design
    assert "Trading Gate" in design or "ASR 밖" in design
    assert "Live Enable" in design or "IPS" in design
    served = TestClient(app).get("/").text
    assert "app.js?v=0.2.79" in served
    assert "styles.css?v=0.2.79" in served
    assert "guideBtn" in served
    assert "guideDialog" in served
