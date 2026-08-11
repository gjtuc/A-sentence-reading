"""서버 STT 인식 (0.3.3 · design/38)."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from sentence_reading.api.app import app
from sentence_reading.stt import recognize as rec

ROOT = Path(__file__).resolve().parents[1]


def test_status_stt_server_flag() -> None:
    st = TestClient(app).get("/api/status").json()
    assert st["version"] == "0.3.16"
    assert st["stt_browser"] is True
    assert "stt_server" in st


def test_design_38_contract() -> None:
    design = (ROOT / "docs" / "design" / "38-stt-server.md").read_text(
        encoding="utf-8"
    )
    assert "0.2.46" in design
    assert "/api/stt/recognize" in design
    assert "점수" in design
    assert "Live Enable" in design or "IPS" in design
    assert "2 MiB" in design or "2MB" in design or "2 MiB" in design


def test_ui_server_wiring() -> None:
    js = (
        ROOT / "src" / "sentence_reading" / "static" / "stt_practice.js"
    ).read_text(encoding="utf-8")
    assert "/api/stt/recognize" in js
    assert "MediaRecorder" in js
    assert "gemini_unavailable" in js
    assert "accuracy" not in js.lower()
    assert "grade" not in js.lower()
    app_js = (ROOT / "src" / "sentence_reading" / "static" / "app.js").read_text(
        encoding="utf-8"
    )
    assert "design/37–38" in app_js or "design/38" in app_js
    assert "stt_server" in app_js
    html = TestClient(app).get("/").text
    assert "stt_practice.js?v=0.3.16" in html
    assert "app.js?v=0.3.16" in html


def test_mime_and_size_edges(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(rec, "gemini_api_key", lambda: "fake")
    assert rec.recognize_english_audio(b"", "audio/webm")["error"] == "empty_audio"
    assert rec.recognize_english_audio(None, "audio/webm")["error"] == "empty_audio"  # type: ignore[arg-type]
    assert (
        rec.recognize_english_audio(b"x", "text/plain")["error"] == "unsupported_mime"
    )
    huge = b"a" * (rec._MAX_BYTES + 1)
    out = rec.recognize_english_audio(huge, "audio/webm")
    assert out["error"] == "too_large"
    assert out["max_bytes"] == rec._MAX_BYTES
    assert rec.mime_allowed("audio/webm;codecs=opus") is True
    assert rec.mime_allowed("image/png") is False
    assert rec.normalize_audio_mime("Audio/WebM;codecs=opus") == "audio/webm"


def test_gemini_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(rec, "gemini_api_key", lambda: "")
    assert (
        rec.recognize_english_audio(b"abcd", "audio/webm")["error"]
        == "gemini_unavailable"
    )


def test_recognize_success_mocked(monkeypatch: pytest.MonkeyPatch) -> None:
    class _Resp:
        text = '  "Hello catalyst."  '
        candidates = []

    class _Models:
        def generate_content(self, **kwargs):  # noqa: ANN003
            return _Resp()

    class _Client:
        def __init__(self, api_key=None):  # noqa: ANN001
            self.models = _Models()

    import sys
    import types as pytypes

    google = pytypes.ModuleType("google")
    google_genai = pytypes.ModuleType("google.genai")
    google_genai_types = pytypes.ModuleType("google.genai.types")

    class _Part:
        @staticmethod
        def from_text(text: str):
            return {"text": text}

        @staticmethod
        def from_bytes(data: bytes, mime_type: str):
            return {"bytes": len(data), "mime": mime_type}

    class _Content:
        def __init__(self, role: str, parts: list):
            self.role = role
            self.parts = parts

    class _Cfg:
        def __init__(self, **kwargs):  # noqa: ANN003
            self.kwargs = kwargs

    google_genai.Client = _Client
    google_genai.types = google_genai_types
    google_genai_types.Part = _Part
    google_genai_types.Content = _Content
    google_genai_types.GenerateContentConfig = _Cfg
    google.genai = google_genai
    monkeypatch.setitem(sys.modules, "google", google)
    monkeypatch.setitem(sys.modules, "google.genai", google_genai)
    monkeypatch.setitem(sys.modules, "google.genai.types", google_genai_types)
    monkeypatch.setattr(rec, "gemini_api_key", lambda: "k")
    monkeypatch.setattr(rec, "gemini_model", lambda: "m")

    out = rec.recognize_english_audio(b"\x00\x01\x02", "audio/webm;codecs=opus")
    assert out["ok"] is True
    assert out["heard"] == "Hello catalyst."
    assert out["engine"] == "gemini"
    assert "score" not in out


def test_api_recognize_edges(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "sentence_reading.api.app.gemini_available", lambda: False
    )
    client = TestClient(app)
    r = client.post(
        "/api/stt/recognize",
        files={"file": ("a.webm", b"abc", "audio/webm")},
        data={"expected": "hi"},
    )
    assert r.json()["error"] == "gemini_unavailable"

    monkeypatch.setattr(
        "sentence_reading.api.app.gemini_available", lambda: True
    )

    def fake(data: bytes, mime: str | None) -> dict:
        return {"ok": True, "heard": "the cat", "engine": "gemini"}

    monkeypatch.setattr(
        "sentence_reading.stt.recognize.recognize_english_audio", fake
    )
    ok = client.post(
        "/api/stt/recognize",
        files={"file": ("a.webm", b"abc", "audio/webm")},
        data={"expected": "the cat sat"},
    )
    body = ok.json()
    assert body["ok"] is True
    assert body["heard"] == "the cat"
    assert body["compare"]["ok"] is True
    assert "score" not in body
    assert "score" not in body["compare"]

    def boom(data: bytes, mime: str | None) -> dict:
        return {"ok": False, "error": "too_large", "max_bytes": 1}

    monkeypatch.setattr(
        "sentence_reading.stt.recognize.recognize_english_audio", boom
    )
    bad = client.post(
        "/api/stt/recognize",
        files={"file": ("a.webm", b"x" * 10, "audio/webm")},
    )
    assert bad.json()["error"] == "too_large"
