"""Flutter mobile TTS contract (0.3.3 · design/33 · design/64)."""

from __future__ import annotations

import re
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from sentence_reading.api.app import app

ROOT = Path(__file__).resolve().parents[1]
MOBILE = ROOT / "mobile"
DESIGN = ROOT / "docs" / "design" / "64-mobile-tts.md"


def test_status_mobile_tts_flag() -> None:
    with TestClient(app) as client:
        st = client.get("/api/status").json()
    assert st["version"] == "0.3.10"
    assert st["mobile_tts"] is True
    assert st["mobile_reader"] is True
    assert "live_enable" not in st
    assert "ips" not in st


def test_tts_empty_text_400() -> None:
    with TestClient(app) as client:
        # May be 503 if credentials missing in CI — either is fine for empty body
        # but empty text should be 400 when TTS available, else 503 before empty check
        r = client.post("/api/tts", json={"text": "   "})
    assert r.status_code in (400, 503)
    body = r.json()
    assert body.get("ok") is False
    if r.status_code == 400:
        assert body.get("error") == "empty_text"


def test_tts_synthesize_mock_bytes() -> None:
    fake = b"ID3fake-mp3-bytes"
    with patch("sentence_reading.api.app.tts_available", return_value=True), patch(
        "sentence_reading.api.app.synthesize_mp3", return_value=fake
    ):
        with TestClient(app) as client:
            r = client.post(
                "/api/tts",
                json={"text": "Hello nickel catalyst.", "speaking_rate": 99},
            )
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("audio/mpeg")
    assert r.content == fake


def test_tts_edge_bad_rate_still_ok_when_mocked() -> None:
    fake = b"\xff\xfb\x90\x00fake"
    with patch("sentence_reading.api.app.tts_available", return_value=True), patch(
        "sentence_reading.api.app.synthesize_mp3", return_value=fake
    ) as syn:
        with TestClient(app) as client:
            r = client.post(
                "/api/tts",
                json={"text": "ok", "speaking_rate": "not-a-number", "voice": "null"},
            )
    assert r.status_code == 200
    # speaking_rate coerced to 1.0 on TypeError
    assert syn.call_args.kwargs.get("speaking_rate") == 1.0 or syn.call_args[1].get(
        "speaking_rate"
    ) == 1.0


def test_mobile_dart_tts_sources() -> None:
    pub = (MOBILE / "pubspec.yaml").read_text(encoding="utf-8")
    assert "0.3.10" in pub
    assert "audioplayers" in pub
    client = (MOBILE / "lib" / "api" / "client.dart").read_text(encoding="utf-8")
    assert "synthesizeTts" in client
    assert "/api/tts" in client
    assert "fetchTtsVoices" in client
    models = (MOBILE / "lib" / "api" / "tts_models.dart").read_text(encoding="utf-8")
    assert "clampSpeakingRate" in models
    assert "isEmptyTtsText" in models
    ctrl = (MOBILE / "lib" / "state" / "tts_controller.dart").read_text(encoding="utf-8")
    assert "playCurrentSentence" in ctrl
    assert "Trading Gate" in ctrl or "ASR" in ctrl or "Live Enable" in ctrl
    reader = (MOBILE / "lib" / "screens" / "reader_screen.dart").read_text(
        encoding="utf-8"
    )
    assert "TtsController" in reader
    assert "playCurrentSentence" in reader or "volume_up" in reader
    # design/96 — speed lives in Settings; practice entry stays on Reader
    assert "'speed'" not in reader and '"speed"' not in reader
    assert "연습" in reader
    settings = (MOBILE / "lib" / "screens" / "settings_screen.dart").read_text(
        encoding="utf-8"
    )
    assert "required this.tts" in settings
    assert "setRate" in settings or "tts.setRate" in settings
    assert "kTtsRatePrefsKey" in ctrl or "asr_tts_rate_v1" in ctrl
    assert "bootstrap" in ctrl
    assert DESIGN.is_file()
    design = DESIGN.read_text(encoding="utf-8")
    assert "0.3.3" in design
    assert "Trading Gate" in design or "ASR" in design


def test_no_secrets_in_mobile_dart() -> None:
    banned = re.compile(
        r"(AIza[0-9A-Za-z_-]{20,}|BEGIN (RSA |EC )?PRIVATE KEY|"
        r"GEMINI_API_KEY|GOOGLE_APPLICATION_CREDENTIALS|"
        r"client_secret|private_key)",
        re.I,
    )
    for path in MOBILE.rglob("*.dart"):
        if "build" in path.parts or ".dart_tool" in path.parts:
            continue
        text = path.read_text(encoding="utf-8")
        assert banned.search(text) is None, f"secret-like in {path}"


def test_html_asset_bust_tracks_app_version() -> None:
    with TestClient(app) as client:
        html = client.get("/").text
    assert "app.js?v=0.3.10" in html
