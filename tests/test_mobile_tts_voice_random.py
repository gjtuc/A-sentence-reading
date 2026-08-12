# -*- coding: utf-8 -*-
"""design/103 — mobile TTS voice + random difficulty (Settings + practice)."""
from __future__ import annotations

import os
import re

from fastapi.testclient import TestClient

from sentence_reading.api.app import app

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MOBILE = os.path.join(ROOT, "mobile")
DESIGN = os.path.join(ROOT, "docs", "design", "103-mobile-tts-voice-random.md")


def test_status_version_pin() -> None:
    with TestClient(app) as client:
        st = client.get("/api/status").json()
    assert st["version"] == "0.3.40"
    assert st["mobile_tts"] is True


def test_design_103_exists() -> None:
    assert os.path.isfile(DESIGN)
    text = open(DESIGN, encoding="utf-8").read()
    assert "0.3.17" in text
    assert "random_normal" in text
    assert "asr_tts_mode_v1" in text
    assert "asr_tts_voice_v1" in text


def test_mobile_tts_models_have_random_pick() -> None:
    models = open(
        os.path.join(MOBILE, "lib", "api", "tts_models.dart"),
        encoding="utf-8",
    ).read()
    assert "pickTtsPlaybackParams" in models
    assert "kTtsModeRandomNormal" in models
    assert "kTtsRateBands" in models
    assert "kTtsLocaleWeights" in models
    assert "en-IN" in models
    assert "ttsModeLabelKo" in models
    assert "TtsVoiceChoice" in models
    # rate bands mirror web
    assert "0.7" in models and "1.3" in models
    assert "1.9" in models


def test_mobile_settings_shows_mode_and_voice() -> None:
    settings = open(
        os.path.join(MOBILE, "lib", "screens", "settings_screen.dart"),
        encoding="utf-8",
    ).read()
    # Korean UI labels (web parity)
    assert "\ubaa8\ub4dc" in settings  # 모드
    assert "\ubaa9\uc18c\ub9ac" in settings  # 목소리
    assert "tts_mode" in settings
    assert "tts_voice" in settings
    assert "setMode" in settings
    assert "setVoice" in settings
    assert "isRandomMode" in settings or "tts.isRandomMode" in settings


def test_tts_controller_persists_mode_voice() -> None:
    ctrl = open(
        os.path.join(MOBILE, "lib", "state", "tts_controller.dart"),
        encoding="utf-8",
    ).read()
    assert "kTtsModePrefsKey" in ctrl or "asr_tts_mode_v1" in ctrl
    assert "kTtsVoicePrefsKey" in ctrl or "asr_tts_voice_v1" in ctrl
    assert "pickPlaybackParams" in ctrl
    assert "ensureVoicesLoaded" in ctrl
    assert "setMode" in ctrl
    assert "setVoice" in ctrl


def test_shadowing_practice_uses_tts_controller() -> None:
    practice = open(
        os.path.join(MOBILE, "lib", "screens", "shadowing_practice_screen.dart"),
        encoding="utf-8",
    ).read()
    reader = open(
        os.path.join(MOBILE, "lib", "screens", "reader_screen.dart"),
        encoding="utf-8",
    ).read()
    assert "required this.tts" in practice
    assert "pickPlaybackParams" in practice
    assert "tts: tts" in reader


def test_pubspec_pin() -> None:
    pub = open(os.path.join(MOBILE, "pubspec.yaml"), encoding="utf-8").read()
    assert "0.3.40" in pub


def test_no_secrets_in_new_dart() -> None:
    banned = re.compile(
        r"(AIza[0-9A-Za-z_-]{20,}|BEGIN (RSA |EC )?PRIVATE KEY|"
        r"GEMINI_API_KEY|GOOGLE_APPLICATION_CREDENTIALS|"
        r"client_secret|private_key)",
        re.I,
    )
    for name in (
        "lib/api/tts_models.dart",
        "lib/state/tts_controller.dart",
        "lib/screens/settings_screen.dart",
        "lib/screens/shadowing_practice_screen.dart",
    ):
        path = os.path.join(MOBILE, name)
        text = open(path, encoding="utf-8").read()
        assert banned.search(text) is None, f"secret-like in {path}"
