"""읽기 live 번역 제거 · 보관본 번역 백필 (0.2.57 · design/42)."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from sentence_reading.api.app import app
from sentence_reading.llm.translate_section import needs_translate_backfill
from sentence_reading.models import Figure, Sentence

ROOT = Path(__file__).resolve().parents[1]


def test_status_ingest_only() -> None:
    st = TestClient(app).get("/api/status").json()
    assert st["version"] == "0.2.57"
    assert st["translate_ingest_only"] is True
    assert st["translate_live_fallback"] is False


def test_design_42_contract() -> None:
    design = (ROOT / "docs" / "design" / "42-translate-ingest-only.md").read_text(
        encoding="utf-8"
    )
    assert "0.2.50" in design
    assert "live" in design.lower() or "실시간" in design
    assert "백필" in design or "backfill" in design.lower()
    assert "Live Enable" in design or "IPS" in design


def test_ui_no_live_translate_fetch() -> None:
    js = (ROOT / "src" / "sentence_reading" / "static" / "app.js").read_text(
        encoding="utf-8"
    )
    assert "미리 번역 없음" in js
    assert "번역 진행 중" in js
    assert "design/42" in js
    assert 'fetch("/api/translate"' not in js
    served = TestClient(app).get("/").text
    assert "app.js?v=0.2.57" in served


def test_needs_backfill_edges() -> None:
    empty = [Sentence(id="s1", text="Hello catalyst.")]
    assert needs_translate_backfill(empty, [], {}) is True
    assert needs_translate_backfill([], [], {}) is False
    filled = [
        Sentence(
            id="s1",
            text="Hi",
            text_ko="안녕",
            text_ko_stage="harmonize",
        )
    ]
    assert (
        needs_translate_backfill(filled, [], {"body": {"en": "x", "ko": "y"}}) is False
    )
    many = [
        Sentence(id=f"s{i}", text=f"t{i}", text_ko="ko" if i == 0 else "")
        for i in range(30)
    ]
    assert needs_translate_backfill(many, [], {}) is True
    dig = {"body": {"en": "x", "ko": "이"}}
    # design/45 — digest만 있고 문장 KO 없으면 이어하기
    assert needs_translate_backfill(empty, [], dig) is True
    figs = [Figure(id="f", image_src="x", caption="c", caption_ko="캡션")]
    assert needs_translate_backfill(empty, figs, {}) is True


def test_api_translate_still_exists() -> None:
    """엔드포인트는 도구용으로 유지 (UI는 안 씀)."""
    r = TestClient(app).post("/api/translate", json={"text": ""})
    assert r.status_code == 200
    assert "ok" in r.json()


def test_backfill_helper_wired() -> None:
    src = (ROOT / "src" / "sentence_reading" / "api" / "app.py").read_text(
        encoding="utf-8"
    )
    assert "_backfill_cached_translations" in src
    assert "needs_translate_backfill" in src
    assert "보관본 번역 채우는 중" in src
