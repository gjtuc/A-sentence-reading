# -*- coding: utf-8 -*-
"""design/219 — TTS voices auth sticky evidence densify."""
from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from sentence_reading.api import app as app_mod
from sentence_reading.llm.evidence_kinds import ALLOWED_KINDS

ROOT = Path(__file__).resolve().parents[1]
MOBILE = ROOT / "mobile"
DESIGN = ROOT / "docs" / "design" / "219-tts-voices-auth-sticky-evidence.md"

_KINDS = (
    "tts_voices_call_start",
    "tts_voices_call_done",
    "tts_auth_sticky",
    "login_gate_deny",
)


@pytest.fixture()
def login_gate_on(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.setenv("ASR_LOGIN_REQUIRED", "1")
    monkeypatch.setenv("ASR_AUTH_SECRET", "login-gate-test-secret")
    monkeypatch.setenv("ASR_GOOGLE_CLIENT_ID", "test-client.apps.googleusercontent.com")
    monkeypatch.setenv("ASR_EMAIL_AUTH", "1")
    monkeypatch.setenv("ASR_EMAIL_PASSWORD", "0")
    monkeypatch.setenv("ASR_EMAIL_MAGIC_LINK", "1")
    monkeypatch.setenv("ASR_EVIDENCE_BUS", "1")
    monkeypatch.setattr(
        "sentence_reading.llm.auth_accounts.project_root", lambda: tmp_path
    )
    yield


def test_design_219_doc() -> None:
    text = DESIGN.read_text(encoding="utf-8")
    assert "tts_voices_call_start" in text
    assert "tts_auth_sticky" in text
    assert "login_gate_deny" in text
    assert "has_token" in text
    assert "login_retry" in text


def test_kinds_allowlisted_py_and_dart() -> None:
    dart = (MOBILE / "lib" / "services" / "evidence_kinds.dart").read_text(
        encoding="utf-8"
    )
    for k in _KINDS:
        assert k in ALLOWED_KINDS
        assert f"'{k}'" in dart


def test_mobile_tts_controller_sensors() -> None:
    ctrl = (MOBILE / "lib" / "state" / "tts_controller.dart").read_text(
        encoding="utf-8"
    )
    assert "tts_voices_call_start" in ctrl
    assert "tts_voices_call_done" in ctrl
    assert "tts_auth_sticky" in ctrl
    assert "retryVoicesAfterAuth" in ctrl
    assert "hasStickyAuthError" in ctrl
    assert "has_token" in ctrl
    assert "login_retry" in ctrl
    assert "stage: 'bootstrap'" in ctrl
    app = (MOBILE / "lib" / "app.dart").read_text(encoding="utf-8")
    assert "retryVoicesAfterAuth" in app
    client = (MOBILE / "lib" / "api" / "client.dart").read_text(encoding="utf-8")
    assert "_breadcrumbApiFail('tts'" in client


def test_anonymous_tts_voices_401_emits_login_gate_deny(
    login_gate_on: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured: list[dict] = []

    def _capture(kind: str, **kwargs):  # type: ignore[no-untyped-def]
        captured.append({"kind": kind, **kwargs})
        return f"ev_test_{len(captured)}"

    import sentence_reading.llm.evidence_bus as eb

    monkeypatch.setattr(eb, "emit", _capture)

    client = TestClient(app_mod.app)
    res = client.get("/api/tts/voices")
    assert res.status_code == 401
    body = res.json()
    assert body.get("error") == "auth_required"
    assert any(e.get("kind") == "login_gate_deny" for e in captured)
    hit = next(e for e in captured if e.get("kind") == "login_gate_deny")
    assert hit.get("code") == "auth_required"
    assert str(hit.get("route") or "").startswith("/api/tts")


def test_status_version_ships_219_sensors() -> None:
    with TestClient(app_mod.app) as client:
        st = client.get("/api/status").json()
    # Bundled with later chips; pin only that version is present and >= 0.3.219.
    ver = str(st.get("version") or "")
    assert ver.count(".") >= 2
    parts = [int(x) for x in ver.split(".")[:3]]
    assert parts >= [0, 3, 219]
