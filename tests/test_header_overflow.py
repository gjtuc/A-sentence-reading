"""헤더 파일 열기 + ⋯ overflow (0.2.66 ship · design/58; 앱 버전은 후속 범프)."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from sentence_reading.api.app import app

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "src" / "sentence_reading" / "static"
APP_JS = STATIC / "app.js"
CSS = STATIC / "styles.css"
INDEX = STATIC / "index.html"
DESIGN = ROOT / "docs" / "design" / "58-header-overflow.md"


def test_status_header_overflow() -> None:
    st = TestClient(app).get("/api/status").json()
    assert st["version"] == "0.2.76"
    assert st["header_overflow"] is True
    assert "live_enable" not in st
    assert "ips" not in st


def test_header_structure() -> None:
    html = INDEX.read_text(encoding="utf-8")
    assert 'id="uploadBtn"' in html
    assert "파일 열기" in html
    assert 'id="headerMoreBtn"' in html
    assert "⋯" in html
    assert 'id="headerMoreMenu"' in html
    # tools live inside menu
    menu_start = html.find('id="headerMoreMenu"')
    assert menu_start > 0
    menu_chunk = html[menu_start : menu_start + 4500]
    for bid in (
        "libraryBtn",
        "translateBtn",
        "sectionReviewBtn",
        "ttsSettingsBtn",
        "sttPracticeBtn",
        "veilBtn",
    ):
        assert f'id="{bid}"' in menu_chunk
    # upload stays outside menu
    before = html[:menu_start]
    assert 'id="uploadBtn"' in before
    assert 'id="translateBtn"' not in before


def test_js_css_wiring() -> None:
    src = APP_JS.read_text(encoding="utf-8")
    assert "design/58" in src
    assert "setHeaderMoreOpen" in src
    assert "toggleHeaderMore" in src
    assert "isHeaderMoreOpen" in src
    assert "headerMoreBtn" in src
    css = CSS.read_text(encoding="utf-8")
    assert ".header-more-menu" in css
    assert "design/58" in css


def test_edge_escape_and_outside_close() -> None:
    src = APP_JS.read_text(encoding="utf-8")
    assert "setHeaderMoreOpen(false)" in src
    # Esc closes menu only when note/review/guide closed
    assert "isNoteOpen() || isSectionReviewOpen() || isGuideOpen()" in src
    # empty/missing nodes: setHeaderMoreOpen guards
    assert "if (!el.headerMoreMenu || !el.headerMoreBtn) return" in src
    # EDGE: stopPropagation on ⋯ so document click does not immediately close
    assert "stopPropagation()" in src
    # EDGE: menuitem close is deferred (handler first)
    assert "setTimeout" in src and "setHeaderMoreOpen(false)" in src
    design = DESIGN.read_text(encoding="utf-8")
    assert "0.2.66" in design
    assert "Trading Gate" in design or "ASR 밖" in design
    assert "Live Enable" in design or "IPS" in design
    served = TestClient(app).get("/").text
    assert "app.js?v=0.2.76" in served
    assert "styles.css?v=0.2.76" in served
    assert "headerMoreBtn" in served
