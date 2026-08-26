# -*- coding: utf-8 -*-
"""design/79 — shadowing practice kill + status flags."""
from __future__ import annotations

import os

from fastapi.testclient import TestClient

from sentence_reading.api import app as app_mod
from sentence_reading.llm import shadowing_practice as sp


def test_shadowing_default_off(monkeypatch) -> None:
    monkeypatch.delenv("ASR_SHADOWING_PRACTICE", raising=False)
    monkeypatch.setenv("ASR_SKIP_ENV_FILE", "1")
    assert sp.shadowing_practice_enabled() is False
    with TestClient(app_mod.app) as client:
        st = client.get("/api/status").json()
    assert st["version"] == "0.3.54"
    assert st["shadowing_practice"] is False
    assert st["mobile_shadowing_practice"] is False


def test_shadowing_kill_on(monkeypatch) -> None:
    monkeypatch.setenv("ASR_SKIP_ENV_FILE", "1")
    monkeypatch.setenv("ASR_SHADOWING_PRACTICE", "1")
    assert sp.shadowing_practice_enabled() is True
    with TestClient(app_mod.app) as client:
        st = client.get("/api/status").json()
    assert st["shadowing_practice"] is True
    assert st["mobile_shadowing_practice"] is True


def test_web_guide_has_shadowing_checkbox() -> None:
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    html = open(
        os.path.join(root, "src", "sentence_reading", "static", "index.html"),
        encoding="utf-8",
    ).read()
    js = open(
        os.path.join(root, "src", "sentence_reading", "static", "app.js"),
        encoding="utf-8",
    ).read()
    assert 'id="shadowingPracticeCheck"' in html
    assert "asr.shadowing.v1" in js
    assert "loadShadowingPrefs" in js
    assert "shadowingPrefs.serverAvailable" in js


def test_mobile_settings_has_shadowing_switch() -> None:
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    settings = open(
        os.path.join(root, "mobile", "lib", "screens", "settings_screen.dart"),
        encoding="utf-8",
    ).read()
    models = open(
        os.path.join(root, "mobile", "lib", "api", "shadowing_models.dart"),
        encoding="utf-8",
    ).read()
    assert "쉐도잉 연습" in settings
    assert "serverAvailable" in settings
    assert "asr.shadowing.v1" in models
    assert "parseShadowingEnabledPref" in models
