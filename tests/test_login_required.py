# -*- coding: utf-8 -*-
"""design/83 — login-required gate (default on; suite conftest forces off)."""
from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from sentence_reading.api import app as app_mod
from sentence_reading.llm.auth_google import AuthUser, issue_session_token
from sentence_reading.llm.login_required import is_login_public_path, login_required_enabled


@pytest.fixture()
def login_gate_on(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.setenv("ASR_LOGIN_REQUIRED", "1")
    monkeypatch.setenv("ASR_AUTH_SECRET", "login-gate-test-secret")
    monkeypatch.setenv("ASR_GOOGLE_CLIENT_ID", "test-client.apps.googleusercontent.com")
    monkeypatch.setenv("ASR_EMAIL_AUTH", "1")
    monkeypatch.setenv("ASR_EMAIL_PASSWORD", "0")
    monkeypatch.setenv("ASR_EMAIL_MAGIC_LINK", "1")
    monkeypatch.setattr(
        "sentence_reading.llm.auth_accounts.project_root", lambda: tmp_path
    )
    yield


def test_login_required_helper_default_on(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ASR_LOGIN_REQUIRED", raising=False)
    monkeypatch.setenv("ASR_SKIP_ENV_FILE", "1")
    assert login_required_enabled() is True
    monkeypatch.setenv("ASR_LOGIN_REQUIRED", "0")
    assert login_required_enabled() is False


def test_public_path_allowlist() -> None:
    assert is_login_public_path("/api/status")
    assert is_login_public_path("/api/auth/status")
    assert is_login_public_path("/api/auth/google")
    assert is_login_public_path("/api/auth/kakao/callback")
    assert is_login_public_path("/api/auth/email/magic/open")
    assert is_login_public_path("/static/app.js")
    assert is_login_public_path("/")
    # Protected surfaces
    assert not is_login_public_path("/api/session/mock")
    assert not is_login_public_path("/api/cache/papers")
    assert not is_login_public_path("/api/auth/email/magic/admin/mint")
    assert not is_login_public_path("/veil.html")
    assert not is_login_public_path("/docs")


def test_status_flag_on(login_gate_on: None) -> None:
    with TestClient(app_mod.app) as client:
        st = client.get("/api/status").json()
    assert st["version"] == "0.3.23"
    assert st["login_required"] is True
    assert st["mobile_login_required"] is True


def test_unauth_protected_api_401(login_gate_on: None) -> None:
    client = TestClient(app_mod.app)
    r = client.get("/api/session/mock")
    assert r.status_code == 401
    body = r.json()
    assert body.get("ok") is False
    assert body.get("error") == "auth_required"
    # EDGE: nonsense path still 401 (not empty success)
    r2 = client.get("/api/cache/papers")
    assert r2.status_code == 401


def test_unauth_public_still_ok(login_gate_on: None) -> None:
    client = TestClient(app_mod.app)
    assert client.get("/api/status").status_code == 200
    assert client.get("/api/auth/status").status_code == 200
    assert client.get("/").status_code == 200
    assert client.get("/static/styles.css").status_code == 200
    # Non-API page → redirect home (login shell)
    r = client.get("/veil.html", follow_redirects=False)
    assert r.status_code in (302, 307)
    assert r.headers.get("location") in ("/", "http://testserver/")


def test_authed_protected_ok(login_gate_on: None) -> None:
    user = AuthUser(
        uid="u_login_gate_a",
        email="a@example.com",
        name="A",
        picture="",
    )
    token = issue_session_token(user)
    client = TestClient(app_mod.app)
    r = client.get("/api/session/mock", cookies={"asr_session": token})
    assert r.status_code == 200
    assert r.json().get("ok") is True


def test_kill_off_allows_anonymous(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ASR_LOGIN_REQUIRED", "0")
    monkeypatch.setenv("ASR_AUTH_SECRET", "login-gate-off")
    monkeypatch.setenv("ASR_GOOGLE_CLIENT_ID", "test-client.apps.googleusercontent.com")
    client = TestClient(app_mod.app)
    st = client.get("/api/status").json()
    assert st["login_required"] is False
    r = client.get("/api/session/mock")
    assert r.status_code == 200


def test_web_boot_has_login_gate_hooks() -> None:
    root = Path(__file__).resolve().parents[1]
    js = (root / "src" / "sentence_reading" / "static" / "app.js").read_text(
        encoding="utf-8"
    )
    css = (root / "src" / "sentence_reading" / "static" / "styles.css").read_text(
        encoding="utf-8"
    )
    assert "asr-login-gate" in js
    assert "login_required" in js
    assert "asr-login-gate" in css
    shell = (root / "mobile" / "lib" / "screens" / "home_shell.dart").read_text(
        encoding="utf-8"
    )
    assert "loginRequired" in shell or "mobileLoginRequired" in shell
