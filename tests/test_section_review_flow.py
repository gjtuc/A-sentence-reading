"""되새김질 이어 보기 (0.2.59 · design/51)."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from sentence_reading.api.app import app

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "src" / "sentence_reading" / "static"


def test_status_section_review_flow() -> None:
    st = TestClient(app).get("/api/status").json()
    assert st["version"] == "0.3.57"
    assert st["section_review_flow"] is True
    assert "live_enable" not in st
    assert "ips" not in st


def test_open_section_review_builds_flow() -> None:
    app_js = (STATIC / "app.js").read_text(encoding="utf-8")
    assert "section-review-flow" in app_js
    assert "design/51" in app_js
    assert "flowEntries" in app_js
    # edge: empty section / no notes → is-empty copy
    assert "이 구간에 아직 기록이 없습니다" in app_js
    assert "이 구간에 문장이 없습니다" in app_js
    # voice stays index-invariant via stopPropagation
    assert "section-review-voice-bar" in app_js
    assert "stopPropagation" in app_js


def test_css_and_design_51() -> None:
    css = (STATIC / "styles.css").read_text(encoding="utf-8")
    assert ".section-review-flow" in css
    assert "word-break: keep-all" in css
    design = (ROOT / "docs/design/51-section-review-flow.md").read_text(encoding="utf-8")
    assert "0.2.59" in design
    assert "Trading Gate" in design or "ASR 밖" in design
    html = TestClient(app).get("/").text
    assert "app.js?v=0.3.57" in html
    assert "styles.css?v=0.3.57" in html
    assert "이어서 봅니다" in (STATIC / "index.html").read_text(encoding="utf-8")
