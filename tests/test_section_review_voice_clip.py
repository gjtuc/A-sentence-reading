"""되새김질 일시 정지 → 클립 다시 듣기/재녹음 (0.2.62 · design/54)."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from sentence_reading.api.app import app

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "src" / "sentence_reading" / "static"
APP_JS = STATIC / "app.js"
CSS = STATIC / "styles.css"
INDEX = STATIC / "index.html"
DESIGN = ROOT / "docs" / "design" / "54-section-review-voice-clip.md"


def test_status_voice_clip_actions() -> None:
    st = TestClient(app).get("/api/status").json()
    assert st["version"] == "0.3.57"
    assert st["section_review_voice_clip_actions"] is True
    assert st["section_review_voice_seq"] is True
    assert "live_enable" not in st
    assert "ips" not in st


def test_clip_action_wiring() -> None:
    src = APP_JS.read_text(encoding="utf-8")
    assert "design/54" in src
    assert "onSectionReviewClipReplay" in src
    assert "onSectionReviewClipRerecord" in src
    assert "onSectionReviewClipEnd" in src
    assert "recordVoiceForSentence" in src
    assert "showSectionReviewClipActions" in src
    assert "⏸ 일시정지" in src or "일시정지" in src
    assert "이 문장만 듣기" in src
    assert "이 문장만 녹음" in src
    assert "clipFinished" in src
    assert "section-review-clip-actions" in src
    css = CSS.read_text(encoding="utf-8")
    assert ".section-review-clip-actions" in css
    html = INDEX.read_text(encoding="utf-8")
    assert "이어" in html
    assert "기록" in html


def test_edge_empty_and_no_mutate_index() -> None:
    src = APP_JS.read_text(encoding="utf-8")
    # empty sid / missing blob guards
    assert "문장 없음" in src
    assert "목소리 없음" in src
    # rerecord must use appendVoiceRevision via recordVoiceForSentence
    start = src.find("async function onSectionReviewClipRerecord")
    end = src.find("\n  function onSectionReviewClipEnd", start)
    assert start > 0 and end > start
    chunk = src[start:end]
    assert "recordVoiceForSentence" in chunk
    assert "sentenceIndex" not in chunk  # does not touch reading index
    # pause must not clear sequence (keepSequence / paused)
    assert "noteUi.voiceSeq.paused = true" in src
    # empty entries early return
    assert "if (!list.length) return" in src

def test_design_and_assets() -> None:
    design = DESIGN.read_text(encoding="utf-8")
    assert "0.2.62" in design
    assert "Trading Gate" in design or "ASR 밖" in design
    served = TestClient(app).get("/").text
    assert "app.js?v=0.3.57" in served
    assert "styles.css?v=0.3.57" in served
