# -*- coding: utf-8 -*-
"""design/133 — logout/account-switch wipes local library/session/draft."""
from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from sentence_reading.api.app import app

ROOT = Path(__file__).resolve().parents[1]
DESIGN = ROOT / "docs" / "design" / "133-logout-session-isolation.md"
APP_DART = ROOT / "mobile" / "lib" / "app.dart"
LIB_CTRL = ROOT / "mobile" / "lib" / "state" / "library_controller.dart"
APP_JS = ROOT / "src" / "sentence_reading" / "static" / "app.js"
PUB = ROOT / "mobile" / "pubspec.yaml"


def test_status_flag_and_version() -> None:
    st = TestClient(app).get("/api/status").json()
    assert st["version"] == "0.3.70"
    assert st["logout_session_isolation"] is True
    assert st["mobile_logout_session_isolation"] is True


def test_design_133_exists() -> None:
    assert DESIGN.is_file()
    text = DESIGN.read_text(encoding="utf-8")
    assert "0.3.49" in text
    assert "clearAll" in text or "로컬" in text
    assert "AccessWaiting" in text or "waiting" in text.lower()


def test_app_root_clears_library_on_logout() -> None:
    text = APP_DART.read_text(encoding="utf-8")
    assert "design/133" in text
    assert "_boundLibraryUid" in text
    assert "clearAll()" in text
    # WHY: must wipe when user is null (AccessWaiting logout path).
    assert "await _library.clearAll()" in text


def test_clear_all_stops_upload_and_clears_draft() -> None:
    text = LIB_CTRL.read_text(encoding="utf-8")
    assert "design/133" in text
    assert "_uploadCancelRequested = true" in text
    # Latch must stay true after wipe (next uploadPdf resets); no mid-wipe re-arm.
    clear_idx = text.find("Future<void> clearAll()")
    assert clear_idx > 0
    clear_body = text[clear_idx : clear_idx + 1200]
    assert "_uploadCancelRequested = false" not in clear_body
    assert "_drafts.clear()" in text
    assert "papers = const []" in text
    assert "session = null" in text


def test_web_logout_wipes_papers() -> None:
    text = APP_JS.read_text(encoding="utf-8")
    assert "design/133" in text
    # Inside logoutAuth — papers emptied before login gate.
    idx = text.find("async function logoutAuth()")
    assert idx > 0
    chunk = text[idx : idx + 2500]
    assert "papers = []" in chunk
    assert "state.sessionId = null" in chunk
    assert "uiPhase = \"boot\"" in chunk


def test_pubspec_version() -> None:
    assert "0.3.70" in PUB.read_text(encoding="utf-8")
