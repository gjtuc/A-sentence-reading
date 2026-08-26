"""design/142 — no keyboard sentence notes (keep recording practice)."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from sentence_reading.api.app import app

ROOT = Path(__file__).resolve().parents[1]
DESIGN = ROOT / "docs" / "design" / "142-no-keyboard-sentence-notes.md"
APP_JS = ROOT / "src" / "sentence_reading" / "static" / "app.js"
INDEX = ROOT / "src" / "sentence_reading" / "static" / "index.html"
PUB = ROOT / "mobile" / "pubspec.yaml"
D141 = ROOT / "docs" / "design" / "141-mobile-sentence-notes.md"


def test_status_default_off() -> None:
    st = TestClient(app).get("/api/status").json()
    assert st["version"] == "0.3.58"
    assert st["sentence_notes_keyboard"] is False
    assert st["mobile_sentence_notes_keyboard"] is False


def test_kill_restore(monkeypatch) -> None:
    monkeypatch.setenv("ASR_SENTENCE_NOTES_KEYBOARD", "1")
    st = TestClient(app).get("/api/status").json()
    assert st["sentence_notes_keyboard"] is True
    monkeypatch.delenv("ASR_SENTENCE_NOTES_KEYBOARD", raising=False)


def test_wiring_and_guide_copy() -> None:
    assert DESIGN.is_file()
    assert "0.3.58" in DESIGN.read_text(encoding="utf-8")
    assert "0.3.58" in PUB.read_text(encoding="utf-8")
    assert "CANCELLED" in D141.read_text(encoding="utf-8")

    js = APP_JS.read_text(encoding="utf-8")
    assert "sentenceNotesKeyboardEnabled" in js
    assert "sentence_notes_keyboard === true" in js
    assert "design/142" in js

    html = INDEX.read_text(encoding="utf-8")
    assert "Enter 노트" not in html
    assert "듣고 적기 노트" not in html
    assert "shadowingPracticeCheck" in html
    assert "sttPracticePanel" in html


def test_asset_pin() -> None:
    html = TestClient(app).get("/").text
    assert "app.js?v=0.3.58" in html
