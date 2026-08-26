# -*- coding: utf-8 -*-
"""design/134 — ingest/upload hang on no progress + error report wiring."""
from __future__ import annotations

import os
from pathlib import Path

from fastapi.testclient import TestClient

os.environ["ASR_SKIP_ENV_FILE"] = "1"
os.environ.pop("ASR_INGEST_UPLOAD_HANG", None)
os.environ.pop("ASR_INGEST_HANG_STALL_SEC", None)

from sentence_reading.api.app import app  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
DESIGN = ROOT / "docs" / "design" / "134-ingest-upload-hang.md"
HANG_DART = ROOT / "mobile" / "lib" / "services" / "hang_watchdog.dart"
LIB = ROOT / "mobile" / "lib" / "state" / "library_controller.dart"
APP_JS = ROOT / "src" / "sentence_reading" / "static" / "app.js"
PUB = ROOT / "mobile" / "pubspec.yaml"


def test_status_hang_flags_and_version() -> None:
    st = TestClient(app).get("/api/status").json()
    assert st["version"] == "0.3.60"
    assert st["ingest_upload_hang"] is True
    assert st["mobile_ingest_upload_hang"] is True
    assert st["ingest_hang_stall_seconds"] == 180


def test_kill_switch_and_stall_sec_env(monkeypatch) -> None:
    monkeypatch.setenv("ASR_INGEST_UPLOAD_HANG", "0")
    monkeypatch.setenv("ASR_INGEST_HANG_STALL_SEC", "8")
    # Re-import helpers via status after env change — functions read env each call.
    from sentence_reading.api import app as app_mod

    assert app_mod._ingest_upload_hang_enabled() is False
    assert app_mod._ingest_hang_stall_seconds() == 8
    st = TestClient(app).get("/api/status").json()
    assert st["ingest_upload_hang"] is False
    assert st["ingest_hang_stall_seconds"] == 8


def test_stall_sec_clamps(monkeypatch) -> None:
    from sentence_reading.api import app as app_mod

    monkeypatch.setenv("ASR_INGEST_HANG_STALL_SEC", "1")
    assert app_mod._ingest_hang_stall_seconds() == 5
    monkeypatch.setenv("ASR_INGEST_HANG_STALL_SEC", "99999")
    assert app_mod._ingest_hang_stall_seconds() == 3600
    monkeypatch.setenv("ASR_INGEST_HANG_STALL_SEC", "nope")
    assert app_mod._ingest_hang_stall_seconds() == 180


def test_design_and_clients_pin() -> None:
    text = DESIGN.read_text(encoding="utf-8")
    # WHY: design/134 ships at 0.3.50; app may be newer — pin the chip version here.
    assert "0.3.50" in text
    assert "ASR_INGEST_UPLOAD_HANG" in text
    assert "자동" in text or "cancel" in text.lower()
    hang = HANG_DART.read_text(encoding="utf-8")
    assert "design/134" in hang
    assert "setLocalHandler" in hang
    assert "ingestStall" in hang
    lib = LIB.read_text(encoding="utf-8")
    assert "_beginIngestHang" in lib
    assert "_noteIngestHangProgress" in lib
    # design/138 — localhost hang simulate surface removed.
    assert "simulateIngestHangForLocalE2E" not in lib
    assert "응답이 없어 업로드를 중단" in lib
    # Must not reset hang on every identical poll (product 2).
    assert "Same place" in lib or "진전" in lib or "do not" in lib.lower()
    js = APP_JS.read_text(encoding="utf-8")
    assert "beginIngestHang" in js
    assert "noteIngestHangProgress" in js
    assert "onIngestHang" in js
    assert "__asrHangE2E" not in js
    assert "0.3.60" in PUB.read_text(encoding="utf-8")
    assert "network_security_config" in (
        ROOT / "mobile/android/app/src/main/AndroidManifest.xml"
    ).read_text(encoding="utf-8")
    nsc = (
        ROOT / "mobile/android/app/src/main/res/xml/network_security_config.xml"
    ).read_text(encoding="utf-8")
    # design/138 — no loopback cleartext exception.
    assert "127.0.0.1" not in nsc
    assert 'cleartextTrafficPermitted="false"' in nsc


def test_logout_test_expects_current_app_version() -> None:
    # 133 design stays historically 0.3.51; runtime version moves with each chip.
    from sentence_reading.api.app import app as live_app

    st = TestClient(live_app).get("/api/status").json()
    assert st["logout_session_isolation"] is True
    assert st["version"] == "0.3.60"
