# -*- coding: utf-8 -*-
"""design/138 — no local-server product path (Live + device only)."""
from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from sentence_reading.api.app import app
from sentence_reading import autostart as autostart_mod

ROOT = Path(__file__).resolve().parents[1]
DESIGN = ROOT / "docs" / "design" / "138-no-local-server-traces.md"
README = ROOT / "README.md"
PUB = ROOT / "mobile" / "pubspec.yaml"
CONFIG = ROOT / "mobile" / "lib" / "config.dart"
SETTINGS = ROOT / "mobile" / "lib" / "screens" / "settings_screen.dart"
LIB = ROOT / "mobile" / "lib" / "state" / "library_controller.dart"
CLIENT = ROOT / "mobile" / "lib" / "api" / "client.dart"
APP_JS = ROOT / "src" / "sentence_reading" / "static" / "app.js"
NSC = ROOT / "mobile" / "android" / "app" / "src" / "main" / "res" / "xml" / "network_security_config.xml"
DEBUG_MANIFEST = ROOT / "mobile" / "android" / "app" / "src" / "debug" / "AndroidManifest.xml"


def test_status_live_only_and_version() -> None:
    st = TestClient(app).get("/api/status").json()
    assert st["version"] == "0.3.64"
    assert st["live_only"] is True
    assert st["mobile_live_only"] is True
    assert st["pipeline_version"] == "rich-v15"


def test_autostart_register_ensure_refuse() -> None:
    # WHY: must not start 127.0.0.1 uvicorn after design/138.
    assert autostart_mod.register_task(quiet=True) == 1
    assert autostart_mod.ensure_server() == 1


def test_docs_and_clients_no_local_surface() -> None:
    assert DESIGN.is_file()
    design = DESIGN.read_text(encoding="utf-8")
    # Historical chip pin stays 0.3.56; runtime version is asserted via status/pubspec.
    assert "0.3.56" in design
    assert "ASR_API_BASE" in design or "Live" in design
    readme = README.read_text(encoding="utf-8")
    assert "로컬 실행" not in readme
    assert "8770" not in readme
    assert "asr-sentence-reading-984608876300" in readme
    assert "0.3.64" in PUB.read_text(encoding="utf-8")
    cfg = CONFIG.read_text(encoding="utf-8")
    assert "fromEnvironment" not in cfg
    assert "ASR_API_BASE" not in cfg
    assert "asia-northeast3.run.app" in cfg
    assert "0.3.64" in cfg
    settings = SETTINGS.read_text(encoding="utf-8")
    assert "hang 시뮬" not in settings
    assert "isLocalDevHost" not in settings
    lib = LIB.read_text(encoding="utf-8")
    assert "simulateIngestHangForLocalE2E" not in lib
    assert "_beginIngestHang" in lib  # hang detection stays
    client = CLIENT.read_text(encoding="utf-8")
    assert "isLocalDevHost" not in client
    js = APP_JS.read_text(encoding="utf-8")
    assert "__asrHangE2E" not in js
    assert "beginIngestHang" in js
    nsc = NSC.read_text(encoding="utf-8")
    assert "127.0.0.1" not in nsc
    assert "localhost" not in nsc
    assert 'cleartextTrafficPermitted="false"' in nsc
    dbg = DEBUG_MANIFEST.read_text(encoding="utf-8")
    assert "usesCleartextTraffic" not in dbg
