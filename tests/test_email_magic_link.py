# -*- coding: utf-8 -*-
"""design/77 — email magic-link mint/redeem + open redirect + access gate stays."""
from __future__ import annotations

import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from sentence_reading.llm import auth_magic_link as ml
from sentence_reading.llm.auth_accounts import lookup_uid, resolve_or_create
from sentence_reading.llm.auth_google import parse_session_token
from sentence_reading.llm.access_gate import public_access_view


@pytest.fixture()
def magic_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("ASR_EMAIL_AUTH", "1")
    monkeypatch.setenv("ASR_EMAIL_MAGIC_LINK", "1")
    monkeypatch.setenv("ASR_AUTH_SECRET", "test-magic-secret")
    monkeypatch.setenv("ASR_ACCESS_GATE", "1")
    monkeypatch.setenv("ASR_ADMIN_EMAILS", "admin@example.com")
    # Isolate auth JSON under tmp.
    monkeypatch.setattr(
        "sentence_reading.cache.paper_cache.project_root", lambda: tmp_path
    )
    monkeypatch.setattr(ml, "project_root", lambda: tmp_path)
    # Avoid GCS side effects.
    monkeypatch.setattr(ml, "_push", lambda *a, **k: None)
    monkeypatch.setattr(ml, "_pull", lambda *a, **k: None)
    yield tmp_path


def test_mint_redeem_single_use(magic_env: Path):
    minted = ml.mint_magic_token("User@Example.COM")
    assert minted["token"]
    em = ml.redeem_magic_token(minted["token"])
    assert em == "user@example.com"
    with pytest.raises(ValueError, match="used"):
        ml.redeem_magic_token(minted["token"])


def test_bad_and_empty_token(magic_env: Path):
    with pytest.raises(ValueError, match="bad_token"):
        ml.redeem_magic_token("")
    with pytest.raises(ValueError, match="bad_token"):
        ml.redeem_magic_token("nope")


def test_kill_switch(magic_env: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("ASR_EMAIL_MAGIC_LINK", "0")
    with pytest.raises(ValueError, match="magic_disabled"):
        ml.mint_magic_token("a@b.co")


def test_open_redirect_sets_session_and_gate_not_auto_allow(
    magic_env: Path, monkeypatch: pytest.MonkeyPatch
):
    # Import app after env/tmp isolation.
    from sentence_reading.api import app as app_mod

    monkeypatch.setattr(
        "sentence_reading.llm.auth_accounts.project_root", lambda: magic_env
    )
    monkeypatch.setattr(
        "sentence_reading.llm.access_gate.project_root", lambda: magic_env
    )
    monkeypatch.setattr(
        "sentence_reading.llm.access_gate._push_auth_json", lambda *a, **k: None
    )
    monkeypatch.setattr(
        "sentence_reading.llm.access_gate._download_auth_json", lambda *a, **k: None
    )

    client = TestClient(app_mod.app)
    st = client.get("/api/status").json()
    assert st["version"] == "0.3.57"
    assert st["mobile_email_magic_link"] is True
    assert st.get("web_email_magic_link_only") is True

    minted = ml.mint_magic_token("reader@example.com")
    # design/85 — default open (no mobile=1) → web cookie + /?auth=
    r = client.get(
        f"/api/auth/email/magic/open?t={minted['token']}", follow_redirects=False
    )
    assert r.status_code == 302
    loc = r.headers.get("location") or ""
    assert loc.startswith("/?auth=logged_in") or loc.endswith("/?auth=logged_in")
    assert "asr_session=" in (r.headers.get("set-cookie") or "")
    # Parse session from Set-Cookie
    from http.cookies import SimpleCookie

    jar = SimpleCookie()
    jar.load(r.headers.get("set-cookie") or "")
    token = jar["asr_session"].value if "asr_session" in jar else ""
    user = parse_session_token(token)
    assert user is not None
    assert user.email.lower() == "reader@example.com"
    # Access gate must NOT auto-allow.
    view = public_access_view(user.uid, email=user.email, is_admin=False)
    assert view.get("status") in ("none", "pending", "denied")
    assert view.get("status") != "allowed"
    assert view.get("can_use_paid") is not True


def test_open_mobile_deep_link(
    magic_env: Path, monkeypatch: pytest.MonkeyPatch
):
    from sentence_reading.api import app as app_mod

    monkeypatch.setattr(
        "sentence_reading.llm.auth_accounts.project_root", lambda: magic_env
    )
    monkeypatch.setattr(
        "sentence_reading.llm.access_gate.project_root", lambda: magic_env
    )
    monkeypatch.setattr(
        "sentence_reading.llm.access_gate._push_auth_json", lambda *a, **k: None
    )
    monkeypatch.setattr(
        "sentence_reading.llm.access_gate._download_auth_json", lambda *a, **k: None
    )

    client = TestClient(app_mod.app)
    minted = ml.mint_magic_token("mobile@example.com")
    r = client.get(
        f"/api/auth/email/magic/open?t={minted['token']}&mobile=1",
        follow_redirects=False,
    )
    assert r.status_code == 302
    loc = r.headers.get("location") or ""
    assert loc.startswith("com.gjtuc.sentence_reading://oauth/magic?")
    assert "asr_session=" in loc
    from urllib.parse import parse_qs

    q = loc.split("?", 1)[-1]
    params = parse_qs(q)
    token = (params.get("asr_session") or [""])[0]
    user = parse_session_token(token)
    assert user is not None
    assert user.email.lower() == "mobile@example.com"
    # Cookie also set so browser Custom Tabs share session if needed.
    assert "asr_session=" in (r.headers.get("set-cookie") or "")


def test_open_bad_token_web_fail_closed(
    magic_env: Path, monkeypatch: pytest.MonkeyPatch
):
    from sentence_reading.api import app as app_mod

    monkeypatch.setattr(
        "sentence_reading.llm.auth_accounts.project_root", lambda: magic_env
    )
    client = TestClient(app_mod.app)
    r = client.get(
        "/api/auth/email/magic/open?t=not-a-real-token",
        follow_redirects=False,
    )
    assert r.status_code == 302
    loc = r.headers.get("location") or ""
    assert "auth_error=" in loc
    # FAIL-CLOSED: no session cookie on bad token.
    assert "asr_session=" not in (r.headers.get("set-cookie") or "")


def test_request_appends_mobile_for_android_client(
    magic_env: Path, monkeypatch: pytest.MonkeyPatch
):
    from sentence_reading.api import app as app_mod

    monkeypatch.setattr(
        "sentence_reading.llm.auth_accounts.project_root", lambda: magic_env
    )
    captured: dict = {}

    def fake_send(*, to_email: str, open_url: str) -> None:
        captured["to"] = to_email
        captured["url"] = open_url

    monkeypatch.setattr(
        "sentence_reading.llm.email_smtp.smtp_configured", lambda: True
    )
    monkeypatch.setattr(
        "sentence_reading.llm.email_smtp.send_magic_link_email", fake_send
    )
    client = TestClient(app_mod.app)
    r = client.post(
        "/api/auth/email/magic/request",
        json={"email": "appuser@example.com", "client": "android"},
    )
    assert r.status_code == 200
    assert captured.get("url", "").endswith("&mobile=1") or "&mobile=1" in captured.get(
        "url", ""
    )
    r2 = client.post(
        "/api/auth/email/magic/request",
        json={"email": "webuser@example.com", "client": "web"},
    )
    assert r2.status_code == 200
    assert "&mobile=1" not in captured.get("url", "")


def test_request_fail_closed_without_smtp(magic_env: Path, monkeypatch: pytest.MonkeyPatch):
    from sentence_reading.api import app as app_mod

    monkeypatch.delenv("ASR_SMTP_HOST", raising=False)
    monkeypatch.delenv("ASR_SMTP_FROM", raising=False)
    monkeypatch.setattr(
        "sentence_reading.llm.auth_accounts.project_root", lambda: magic_env
    )
    client = TestClient(app_mod.app)
    r = client.post(
        "/api/auth/email/magic/request", json={"email": "x@example.com"}
    )
    assert r.status_code == 503
    body = r.json()
    assert body.get("ok") is False
    assert body.get("error") == "smtp_not_configured"


def test_admin_mint_requires_admin(magic_env: Path, monkeypatch: pytest.MonkeyPatch):
    from sentence_reading.api import app as app_mod

    monkeypatch.setattr(
        "sentence_reading.llm.auth_accounts.project_root", lambda: magic_env
    )
    client = TestClient(app_mod.app)
    r = client.post(
        "/api/auth/email/magic/admin/mint", json={"email": "x@example.com"}
    )
    assert r.status_code == 403


def test_passwordless_create_then_password_login_fails(
    magic_env: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(
        "sentence_reading.llm.auth_accounts.project_root", lambda: magic_env
    )
    u = resolve_or_create("email", "pwless@example.com", email="pwless@example.com", password=None)
    assert u.email == "pwless@example.com"
    assert lookup_uid("email", "pwless@example.com") == u.uid
    from sentence_reading.api import app as app_mod

    client = TestClient(app_mod.app)
    r = client.post(
        "/api/auth/email/login",
        json={"email": "pwless@example.com", "password": "password1"},
    )
    assert r.status_code == 401
