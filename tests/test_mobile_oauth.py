"""Flutter mobile Google/Kakao OAuth wiring (0.2.73 · design/65)."""

from __future__ import annotations

import re
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from sentence_reading.api.app import app
from sentence_reading.llm import auth_accounts as aa
from sentence_reading.llm import auth_google as ag
from sentence_reading.llm.auth_google import AuthUser, issue_oauth_state, mobile_kakao_deep_link

ROOT = Path(__file__).resolve().parents[1]
MOBILE = ROOT / "mobile"
DESIGN = ROOT / "docs" / "design" / "65-mobile-oauth.md"


@pytest.fixture(autouse=True)
def _iso(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.setenv("ASR_EMAIL_AUTH", "1")
    monkeypatch.setenv("ASR_AUTH_SECRET", "oauth-mobile-test-secret")
    monkeypatch.setenv("ASR_GOOGLE_CLIENT_ID", "cid.apps.googleusercontent.com")
    monkeypatch.setenv("ASR_KAKAO_REST_API_KEY", "kakao-rest-test")
    root = tmp_path / "proj"
    root.mkdir()
    (root / "pyproject.toml").write_text("[project]\nname='t'\n", encoding="utf-8")
    monkeypatch.setattr(aa, "project_root", lambda: root)
    monkeypatch.setattr(aa, "accounts_path", lambda: root / "data" / "auth" / "accounts.json")
    ag.reset_gcs_uid()
    yield
    ag.reset_gcs_uid()


def test_status_mobile_oauth_flag() -> None:
    with TestClient(app) as client:
        st = client.get("/api/status").json()
    assert st["version"] == "0.2.73"
    assert st["mobile_oauth"] is True
    assert st["mobile_tts"] is True
    assert "live_enable" not in st
    assert "ips" not in st


def test_oauth_state_mobile_roundtrip() -> None:
    s = issue_oauth_state("login", mobile=True)
    p = ag.parse_oauth_state(s)
    assert p is not None
    assert p["mobile"] == "1"
    assert ag.parse_oauth_state(issue_oauth_state("login", mobile=False))["mobile"] == "0"


def test_mobile_kakao_deep_link_edges() -> None:
    ok = mobile_kakao_deep_link(session="tok.abc", auth="logged_in")
    assert ok.startswith("com.gjtuc.sentence_reading://oauth/kakao?")
    assert "asr_session=tok.abc" in ok
    err = mobile_kakao_deep_link(error="bad_state")
    assert "auth_error=bad_state" in err


def test_kakao_callback_mobile_deep_link(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_exchange(code: str, *, redirect_uri: str):
        assert code == "good-code"
        return {
            "subject": "kakao-99",
            "email": "k@example.com",
            "name": "K",
            "picture": "",
        }

    monkeypatch.setattr("sentence_reading.api.app.kakao_exchange_code", fake_exchange)
    state = issue_oauth_state("login", mobile=True)
    client = TestClient(app, follow_redirects=False)
    r = client.get(
        "/api/auth/kakao/callback",
        params={"code": "good-code", "state": state},
    )
    assert r.status_code == 302
    loc = r.headers["location"]
    assert loc.startswith("com.gjtuc.sentence_reading://oauth/kakao?")
    assert "asr_session=" in loc
    assert "auth=logged_in" in loc


def test_kakao_callback_web_unchanged(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_exchange(code: str, *, redirect_uri: str):
        return {"subject": "kakao-1", "email": "", "name": "W", "picture": ""}

    monkeypatch.setattr("sentence_reading.api.app.kakao_exchange_code", fake_exchange)
    state = issue_oauth_state("login", mobile=False)
    client = TestClient(app, follow_redirects=False)
    r = client.get(
        "/api/auth/kakao/callback",
        params={"code": "c", "state": state},
    )
    assert r.status_code == 302
    assert r.headers["location"].startswith("/?auth=")


def test_kakao_callback_bad_state_mobile() -> None:
    client = TestClient(app, follow_redirects=False)
    # craft mobile-looking failure: no state → web err (not mobile)
    r = client.get("/api/auth/kakao/callback", params={"code": "x", "state": "nope"})
    assert r.status_code == 302
    assert "auth_error" in r.headers["location"]


def test_google_login_still_works(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_verify(cred: str) -> AuthUser:
        assert cred == "a.b.c.d.e.f.g.h.i.j.k"
        return AuthUser(uid="118234567890123456789", email="g@x.com", name="G")

    monkeypatch.setattr("sentence_reading.api.app.verify_google_id_token", fake_verify)
    client = TestClient(app)
    r = client.post("/api/auth/google", json={"credential": "a.b.c.d.e.f.g.h.i.j.k"})
    assert r.status_code == 200
    assert r.json()["user"]["uid"]


def test_mobile_dart_oauth_sources() -> None:
    pub = (MOBILE / "pubspec.yaml").read_text(encoding="utf-8")
    assert "0.2.73" in pub
    assert "google_sign_in" in pub
    assert "flutter_web_auth_2" in pub
    client = (MOBILE / "lib" / "api" / "client.dart").read_text(encoding="utf-8")
    assert "loginGoogle" in client and "applySessionToken" in client
    assert "kakaoStartUrl" in client
    models = (MOBILE / "lib" / "api" / "oauth_models.dart").read_text(encoding="utf-8")
    assert "parseKakaoDeepLink" in models
    assert "isUsableGoogleCredential" in models
    login = (MOBILE / "lib" / "screens" / "login_screen.dart").read_text(encoding="utf-8")
    assert "Google로 계속" in login and "카카오로 계속" in login
    manifest = (
        MOBILE / "android" / "app" / "src" / "main" / "AndroidManifest.xml"
    ).read_text(encoding="utf-8")
    assert "com.gjtuc.sentence_reading" in manifest
    assert "oauth" in manifest
    assert DESIGN.is_file()
    design = DESIGN.read_text(encoding="utf-8")
    assert "0.2.73" in design
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
    assert "app.js?v=0.2.73" in html
