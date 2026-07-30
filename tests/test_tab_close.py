"""논문 탭 × 닫기 (0.2.42 · design/34)."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from sentence_reading.api.app import app

ROOT = Path(__file__).resolve().parents[1]


def test_status_version() -> None:
    st = TestClient(app).get("/api/status").json()
    assert st["version"] == "0.2.62"


def test_design_tab_close_contract() -> None:
    design = (ROOT / "docs" / "design" / "34-tab-close.md").read_text(encoding="utf-8")
    assert "0.2.42" in design
    assert "탭 범위" in design
    assert "TTS" in design
    assert "Live Enable" in design or "IPS" in design


def test_app_js_has_close_helpers() -> None:
    js = (ROOT / "src" / "sentence_reading" / "static" / "app.js").read_text(
        encoding="utf-8"
    )
    assert "function closePaperTab" in js
    assert "paper-tab-close" in js
    assert "design/34" in js
    # 전역 TTS/테마는 닫기 경로에서 건드리지 않음
    close_block = js.split("async function closePaperTab", 1)[1].split(
        "function advancePaper", 1
    )[0]
    assert "ttsSettings" not in close_block
    assert "persistReadingProgress" in close_block
    assert "flushNoteSave" in close_block


def test_index_assets_version() -> None:
    html = TestClient(app).get("/").text
    assert "app.js?v=0.2.62" in html
