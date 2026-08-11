# -*- coding: utf-8 -*-
"""design/78 — email password signup/login off by default."""
from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from sentence_reading.api import app as app_mod


@pytest.fixture()
def password_off(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.setenv("ASR_EMAIL_AUTH", "1")
    monkeypatch.setenv("ASR_EMAIL_PASSWORD", "0")
    monkeypatch.setenv("ASR_EMAIL_MAGIC_LINK", "1")
    monkeypatch.setenv("ASR_AUTH_SECRET", "pw-off-test")
    monkeypatch.setattr(
        "sentence_reading.llm.auth_accounts.project_root", lambda: tmp_path
    )
    yield


def test_status_password_flag_off(password_off: None) -> None:
    with TestClient(app_mod.app) as client:
        st = client.get("/api/status").json()
    assert st["version"] == "0.3.2"
    assert st["mobile_email_password"] is False
    assert st["mobile_password_ui"] is False
    assert st["mobile_email_magic_link"] is True


def test_register_login_fail_closed(password_off: None) -> None:
    client = TestClient(app_mod.app)
    r = client.post(
        "/api/auth/email/register",
        json={"email": "x@example.com", "password": "password1"},
    )
    assert r.status_code == 503
    assert r.json().get("error") == "email_password_disabled"
    r2 = client.post(
        "/api/auth/email/login",
        json={"email": "x@example.com", "password": "password1"},
    )
    assert r2.status_code == 503
    assert r2.json().get("error") == "email_password_disabled"


def test_login_screen_has_no_password_fields() -> None:
    root = Path(__file__).resolve().parents[1]
    login = (root / "mobile" / "lib" / "screens" / "login_screen.dart").read_text(
        encoding="utf-8"
    )
    assert "이메일로 로그인 링크 받기" in login
    assert "Google로 계속" in login
    assert "_registerMode" not in login
    assert "비밀번호" not in login
    assert "validateRegisterPasswords" not in login
    assert "registerEmail" not in login
    assert "loginEmail" not in login
