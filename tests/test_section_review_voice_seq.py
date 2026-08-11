"""되새김질 목소리 이어 듣기 (0.2.60 · design/52)."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from sentence_reading.api.app import app

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "src" / "sentence_reading" / "static"
APP_JS = STATIC / "app.js"
CSS = STATIC / "styles.css"
INDEX = STATIC / "index.html"
DESIGN = ROOT / "docs" / "design" / "52-section-review-voice-seq.md"


def test_status_section_review_voice_seq() -> None:
    st = TestClient(app).get("/api/status").json()
    assert st["version"] == "0.3.19"
    assert st["section_review_flow"] is True
    assert st["section_review_voice_seq"] is True
    # Live Enable / IPS = Trading Gate only (ASR 밖)
    assert "live_enable" not in st
    assert "ips" not in st


def test_sequence_wiring_and_invariants() -> None:
    src = APP_JS.read_text(encoding="utf-8")
    assert "onSectionReviewPlayVoiceSequence" in src
    assert "design/52" in src
    assert "▶ 이어 듣기" in src
    assert "keepSequence" in src
    assert "voiceSeqGen" in src
    assert "section-review-voice-seq" in src
    # 번호 ▶ 나열 UI 제거 (시퀀스 버튼만)
    assert 'playBtn.textContent = "▶ " + (vi + 1)' not in src
    # 시퀀스 재생이 store 를 바꾸지 않음
    start = src.find("async function onSectionReviewPlayVoiceSequence")
    assert start > 0
    end = src.find("\n  async function ", start + 10)
    if end < 0:
        end = src.find("\n  function ", start + 10)
    chunk = src[start:end]
    assert "appendVoiceRevision" not in chunk
    assert "playVoiceBlobKey" in chunk


def test_edge_empty_and_missing_handled() -> None:
    """말도 안 되는 입력 — 빈 entries / 빈 blobKey 는 조기 반환·필터."""
    src = APP_JS.read_text(encoding="utf-8")
    assert "if (!list.length) return" in src
    assert "keepSequence: true" in src
    seq_start = src.find("async function onSectionReviewPlayVoiceSequence")
    seq_end = src.find("\n  async function onSectionReviewClipReplay", seq_start + 10)
    assert seq_start > 0 and seq_end > seq_start
    seq = src[seq_start:seq_end]
    assert "function advance()" in seq
    assert "if (!ok) advance()" in seq
    assert "noteUi.voiceSeq.i !== i" in seq
    assert "onMissing:" not in seq
    assert "paused" in seq


def test_css_html_design_52() -> None:
    css = CSS.read_text(encoding="utf-8")
    assert ".section-review-voice-seq" in css
    html = INDEX.read_text(encoding="utf-8")
    assert "이어 듣기" in html
    app_src = APP_JS.read_text(encoding="utf-8")
    assert "일시정지" in app_src
    design = DESIGN.read_text(encoding="utf-8")
    assert "0.2.60" in design
    assert "Trading Gate" in design or "ASR 밖" in design
    served = TestClient(app).get("/").text
    assert "app.js?v=0.3.19" in served
    assert "styles.css?v=0.3.19" in served
