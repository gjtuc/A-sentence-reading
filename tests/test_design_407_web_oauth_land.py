"""design/407 - Google and Kakao log the web app in and land back on /app/."""

from __future__ import annotations

import urllib.parse

import pytest
from fastapi.testclient import TestClient

from sentence_reading.llm.auth_google import issue_oauth_state, parse_oauth_state


@pytest.fixture()
def client(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("ASR_AUTH_SECRET", "test-407-secret")
    from sentence_reading.api import app as app_mod

    return TestClient(app_mod.app), app_mod


def test_state_carries_land_app_only_when_asked(client):
    assert parse_oauth_state(issue_oauth_state("login", land="app"))["land"] == "app"
    assert parse_oauth_state(issue_oauth_state("login"))["land"] == ""
    assert parse_oauth_state(issue_oauth_state("login", mobile=True, land="evil"))["land"] == ""


def test_kakao_callback_errors_land_on_the_page_that_asked(client):
    c, _ = client
    for land, root in (("app", "/app/"), ("", "/")):
        state = issue_oauth_state("login", land=land)
        r = c.get(
            "/api/auth/kakao/callback?" + urllib.parse.urlencode({"state": state, "error": "access_denied"}),
            follow_redirects=False,
        )
        assert r.status_code == 302
        assert r.headers["location"] == root + "?auth_error=kakao_access_denied"


def test_kakao_callback_success_lands_on_app_with_cookie(client, monkeypatch: pytest.MonkeyPatch):
    c, app_mod = client
    monkeypatch.setattr(app_mod, "kakao_exchange_code", lambda code, redirect_uri: {"subject": "k1", "email": "k@example.com"})
    monkeypatch.setattr(app_mod, "resolve_or_create", lambda *a, **k: app_mod.AuthUser(uid="u-407", email="k@example.com"))
    state = issue_oauth_state("login", land="app")
    r = c.get(
        "/api/auth/kakao/callback?" + urllib.parse.urlencode({"state": state, "code": "c"}),
        follow_redirects=False,
    )
    assert r.status_code == 302
    assert r.headers["location"] == "/app/?auth=logged_in"
    assert "asr_session=" in (r.headers.get("set-cookie") or "")


def test_google_page_for_web_app_goes_back_to_app(client, monkeypatch: pytest.MonkeyPatch):
    c, app_mod = client
    monkeypatch.setattr(app_mod, "auth_client_id", lambda: "cid.apps")
    web = c.get("/api/auth/google/mobile/start?mode=login&land=app").text
    assert 'var LAND = "app";' in web
    assert "window.location.href = '/app/?auth='" in web
    assert "mobile: LAND ? '0' : '1'" in web
    phone = c.get("/api/auth/google/mobile/start?mode=login").text
    assert 'var LAND = "";' in phone
