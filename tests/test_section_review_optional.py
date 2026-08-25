"""되새김질 on/off 옵션 (0.2.61 · design/53)."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from sentence_reading.api.app import app

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "src" / "sentence_reading" / "static"
APP_JS = STATIC / "app.js"
CSS = STATIC / "styles.css"
INDEX = STATIC / "index.html"
DESIGN = ROOT / "docs" / "design" / "53-section-review-optional.md"


def test_status_section_review_optional() -> None:
    st = TestClient(app).get("/api/status").json()
    assert st["version"] == "0.3.52"
    assert st["section_review_optional"] is True
    assert st["section_review_flow"] is True
    # Live Enable / IPS = Trading Gate only (ASR 밖)
    assert "live_enable" not in st
    assert "ips" not in st


def test_pref_wiring_and_gate() -> None:
    src = APP_JS.read_text(encoding="utf-8")
    assert "sectionReviewPrefs" in src
    assert "asr.sectionReview.v1" in src
    assert "loadSectionReviewPrefs" in src
    assert "design/53" in src
    assert "crossedForward && sectionReviewPrefs.enabled" in src
    assert "if (!sectionReviewPrefs.enabled) return" in src
    # 기본 켜짐
    assert "const sectionReviewPrefs = { enabled: true }" in src
    html = INDEX.read_text(encoding="utf-8")
    assert 'id="sectionReviewBtn"' in html
    assert "되새김" in html
    css = CSS.read_text(encoding="utf-8")
    assert "#sectionReviewBtn[aria-pressed=" in css


def test_edge_corrupt_prefs_default_on() -> None:
    """말도 안 되는 localStorage — catch·기본 켜짐 복구 경로가 있어야 함."""
    src = APP_JS.read_text(encoding="utf-8")
    start = src.find("function loadSectionReviewPrefs")
    end = src.find("\n  function saveSectionReviewPrefs", start)
    assert start > 0 and end > start
    chunk = src[start:end]
    assert "sectionReviewPrefs.enabled = true" in chunk
    assert "catch" in chunk
    assert 'typeof data === "boolean"' in chunk


def test_toggle_closes_open_review() -> None:
    src = APP_JS.read_text(encoding="utf-8")
    assert "el.sectionReviewBtn.addEventListener" in src
    assert "closeSectionReview({ resume: false })" in src
    design = DESIGN.read_text(encoding="utf-8")
    assert "0.2.61" in design
    assert "Trading Gate" in design or "ASR 밖" in design
    served = TestClient(app).get("/").text
    assert "app.js?v=0.3.52" in served
    assert "styles.css?v=0.3.52" in served
    assert "sectionReviewBtn" in served
