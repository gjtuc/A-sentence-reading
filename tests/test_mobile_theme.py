"""Flutter mobile theme prefs (0.2.96 · design/33 · design/66)."""

from __future__ import annotations

import re
from pathlib import Path

from fastapi.testclient import TestClient

from sentence_reading.api.app import app

ROOT = Path(__file__).resolve().parents[1]
MOBILE = ROOT / "mobile"
DESIGN = ROOT / "docs" / "design" / "66-mobile-theme.md"


def test_status_mobile_theme_flag() -> None:
    with TestClient(app) as client:
        st = client.get("/api/status").json()
    assert st["version"] == "0.2.96"
    assert st["mobile_theme"] is True
    assert st["mobile_oauth"] is True
    assert "live_enable" not in st
    assert "ips" not in st


def test_mobile_dart_theme_sources() -> None:
    pub = (MOBILE / "pubspec.yaml").read_text(encoding="utf-8")
    assert "0.2.96" in pub
    models = (MOBILE / "lib" / "api" / "theme_models.dart").read_text(
        encoding="utf-8"
    )
    assert "parseThemeModePref" in models
    assert "serializeThemeModePref" in models
    assert "asr.theme.v1" in models
    store = (MOBILE / "lib" / "api" / "theme_store.dart").read_text(encoding="utf-8")
    assert "MemoryThemeStore" in store
    ctrl = (MOBILE / "lib" / "state" / "theme_controller.dart").read_text(
        encoding="utf-8"
    )
    assert "setMode" in ctrl and "bootstrap" in ctrl
    settings = (MOBILE / "lib" / "screens" / "settings_screen.dart").read_text(
        encoding="utf-8"
    )
    assert "SegmentedButton" in settings
    # WHY: user-facing Settings must not show Trading Gate / Live Enable copy.
    assert "Live Enable" not in settings
    assert "Trading Gate" not in settings
    app = (MOBILE / "lib" / "app.dart").read_text(encoding="utf-8")
    assert "themeMode:" in app and "darkTheme:" in app
    shell = (MOBILE / "lib" / "screens" / "home_shell.dart").read_text(
        encoding="utf-8"
    )
    assert "SettingsScreen" in shell
    assert "label: '보관'" in shell
    assert "label: '서버'" not in shell
    assert DESIGN.is_file()
    design = DESIGN.read_text(encoding="utf-8")
    assert "0.2.96" in design
    assert "Trading Gate" in design or "ASR" in design


def test_no_secrets_in_mobile_dart() -> None:
    banned = re.compile(
        r"(AIza[0-9A-Za-z_-]{20,}|BEGIN (RSA |EC )?PRIVATE KEY|"
        r"GEMINI_API_KEY|GOOGLE_APPLICATION_CREDENTIALS|"
        r"ASR_KAKAO_CLIENT_SECRET|client_secret|private_key)",
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
    assert "app.js?v=0.2.96" in html
