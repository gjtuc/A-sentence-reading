"""분기 리뷰 목소리 재생 UI 계약 (정적 검사)."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "src" / "sentence_reading" / "static"
APP_JS = STATIC / "app.js"
INDEX = STATIC / "index.html"
CSS = STATIC / "styles.css"
NOTES = STATIC / "notes_revisions.js"


def test_latest_voice_api_exists() -> None:
    src = NOTES.read_text(encoding="utf-8")
    assert "latestVoice" in src
    assert "appendVoiceRevision" in src


def test_section_review_voice_wiring() -> None:
    app = APP_JS.read_text(encoding="utf-8")
    assert "section-review-voice-btn" in app
    assert "onSectionReviewPlayVoice" in app
    assert "playVoiceBlobKey" in app
    assert "stopVoicePlayback" in app
    # INVARIANT: voice click must not rely solely on row pick
    assert "stopPropagation" in app
    assert "voicePlayingKey" in app


def test_section_review_hint_mentions_voice() -> None:
    html = INDEX.read_text(encoding="utf-8")
    assert "목소리" in html
    css = CSS.read_text(encoding="utf-8")
    assert ".section-review-voice-btn" in css
    assert ".section-review-row" in css


def test_voice_play_does_not_mutate_store_contract() -> None:
    """재생은 blob 읽기만 — notes store append 경로를 타지 않음."""
    app = APP_JS.read_text(encoding="utf-8")
    # onSectionReviewPlayVoice 본문에 appendVoiceRevision 호출이 없어야 함
    start = app.find("async function onSectionReviewPlayVoice")
    assert start > 0
    end = app.find("\n  async function ", start + 10)
    if end < 0:
        end = app.find("\n  function ", start + 10)
    chunk = app[start:end]
    assert "appendVoiceRevision" not in chunk
    assert "playVoiceBlobKey" in chunk


if __name__ == "__main__":
    test_latest_voice_api_exists()
    test_section_review_voice_wiring()
    test_section_review_hint_mentions_voice()
    test_voice_play_does_not_mutate_store_contract()
    print("ok: test_section_review_voice")
