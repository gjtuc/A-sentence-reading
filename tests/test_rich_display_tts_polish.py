# -*- coding: utf-8 -*-
"""Rich display + TTS polish contract (0.3.4 · design/88)."""
from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from sentence_reading.api.app import app
from sentence_reading.llm.tts_speak import spoken_text_for_tts

ROOT = Path(__file__).resolve().parents[1]


def test_status_version_0_3_4() -> None:
    client = TestClient(app)
    st = client.get("/api/status").json()
    assert st["version"] == "0.3.4"


def test_design_88_exists() -> None:
    p = ROOT / "docs" / "design" / "88-rich-display-tts-polish.md"
    assert p.is_file()
    text = p.read_text(encoding="utf-8")
    assert "0.3.4" in text
    assert "TTS" in text


def test_flutter_rich_sentence_module() -> None:
    dart = ROOT / "mobile" / "lib" / "api" / "rich_sentence.dart"
    assert dart.is_file()
    body = dart.read_text(encoding="utf-8")
    assert "buildRichSpans" in body
    assert "sub" in body


def test_web_client_sanitize_present() -> None:
    js = (ROOT / "src" / "sentence_reading" / "static" / "app.js").read_text(
        encoding="utf-8"
    )
    assert "sanitizeSentenceHtmlClient" in js
    assert "setSentenceKoDisplay" in js


def test_tts_cm_inverse_contract() -> None:
    assert "per centimeter" in spoken_text_for_tts("1650 cm<sup>−1</sup>").lower()
