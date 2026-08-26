"""design/146a — mobile Settings account link/unlink."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from sentence_reading.api.app import app
from sentence_reading.llm import auth_accounts as aa
from sentence_reading.llm import auth_google as ag
from sentence_reading.llm import auth_magic_link as ml
from sentence_reading.llm.auth_google import AuthUser

ROOT = Path(__file__).resolve().parents[1]
MOBILE = ROOT / "mobile"
DESIGN = ROOT / "docs" / "design" / "146a-mobile-account-link.md"
DESIGN_146C = ROOT / "docs" / "design" / "146c-mobile-kakao-oauth-scheme.md"


@pytest.fixture(autouse=True)
def _iso(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.setenv("ASR_EMAIL_AUTH", "1")
    monkeypatch.setenv("ASR_EMAIL_MAGIC_LINK", "1")
    monkeypatch.setenv("ASR_AUTH_SECRET", "link-mobile-test-secret")
    monkeypatch.setenv("ASR_GOOGLE_CLIENT_ID", "cid.apps.googleusercontent.com")
    monkeypatch.setenv("ASR_KAKAO_REST_API_KEY", "kakao-rest-test")
    root = tmp_path / "proj"
    root.mkdir()
    (root / "pyproject.toml").write_text("[project]\nname='t'\n", encoding="utf-8")
    monkeypatch.setattr(aa, "project_root", lambda: root)
    monkeypatch.setattr(aa, "accounts_path", lambda: root / "data" / "auth" / "accounts.json")
    monkeypatch.setattr(ml, "project_root", lambda: root)
    ag.reset_gcs_uid()
    yield
    ag.reset_gcs_uid()


def test_status_mobile_account_link() -> None:
    st = TestClient(app).get("/api/status").json()
    assert st["version"] == "0.3.65"
    assert st["mobile_account_link"] is True
    assert "live_enable" not in st
    assert "ips" not in st


def test_mobile_dart_link_wiring() -> None:
    assert DESIGN.is_file()
    design = DESIGN.read_text(encoding="utf-8")
    assert "0.3.63" in design  # 146a ship pin
    assert "146b" in design  # warehouse merge deferred
    assert DESIGN_146C.is_file()
    assert "0.3.65" in DESIGN_146C.read_text(encoding="utf-8")
    screen = (MOBILE / "lib/screens/settings_screen.dart").read_text(encoding="utf-8")
    assert "계정 연결" in screen
    assert "linkGoogle" in screen and "linkKakao" in screen
    assert "requestEmailLink" in screen
    assert "unlinkProvider" in screen
    client = (MOBILE / "lib/api/client.dart").read_text(encoding="utf-8")
    assert "resolveKakaoLinkAuthorizeUrl" in client
    assert "followRedirects = false" in client or "followRedirects=false" in client
    assert "requestEmailLinkMagic" in client
    assert "unlinkProvider" in client
    authc = (MOBILE / "lib/state/auth_controller.dart").read_text(encoding="utf-8")
    assert "linkGoogle" in authc and "linkKakao" in authc
    pub = (MOBILE / "pubspec.yaml").read_text(encoding="utf-8")
    assert "0.3.65" in pub


def test_kakao_link_start_requires_session() -> None:
    client = TestClient(app, follow_redirects=False)
    r = client.get("/api/auth/kakao/start", params={"mode": "link", "mobile": "1"})
    assert r.status_code == 401


def test_kakao_link_start_with_session_redirects(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    u = aa.resolve_or_create(
        "google", "118234567890123456789", email="a@x.com", name="A"
    )
    from sentence_reading.llm.auth_google import issue_session_token

    tok = issue_session_token(u)
    client = TestClient(app, follow_redirects=False)
    r = client.get(
        "/api/auth/kakao/start",
        params={"mode": "link", "mobile": "1"},
        cookies={"asr_session": tok},
    )
    assert r.status_code == 302
    loc = r.headers.get("location") or ""
    assert "kauth.kakao.com" in loc or "kakao" in loc.lower()


def test_google_link_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_verify(cred: str) -> AuthUser:
        return AuthUser(uid="118234567890123456799", email="b@x.com", name="B")

    monkeypatch.setattr("sentence_reading.api.app.verify_google_id_token", fake_verify)
    primary = aa.resolve_or_create(
        "email", "primary@example.com", email="primary@example.com", password="password1"
    )
    from sentence_reading.llm.auth_google import issue_session_token

    tok = issue_session_token(primary)
    client = TestClient(app)
    r = client.post(
        "/api/auth/google",
        json={"credential": "a.b.c.d.e.f.g.h.i.j.k", "mode": "link"},
        cookies={"asr_session": tok},
    )
    assert r.status_code == 200
    providers = r.json()["user"]["providers"]
    assert "email" in providers and "google" in providers
    assert r.json()["user"]["uid"] == primary.uid


def test_magic_link_intent_link(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "sentence_reading.llm.email_smtp.smtp_configured", lambda: True
    )
    sent: list[str] = []

    def fake_send(*, to_email: str, open_url: str) -> None:
        sent.append(open_url)

    monkeypatch.setattr(
        "sentence_reading.llm.email_smtp.send_magic_link_email", fake_send
    )
    primary = aa.resolve_or_create(
        "google", "118234567890123456789", email="g@x.com", name="G"
    )
    from sentence_reading.llm.auth_google import issue_session_token

    tok = issue_session_token(primary)
    client = TestClient(app)
    # EDGE: no session → 401
    deny = client.post(
        "/api/auth/email/magic/request",
        json={"email": "linkme@example.com", "intent": "link", "client": "android"},
    )
    assert deny.status_code == 401

    ok = client.post(
        "/api/auth/email/magic/request",
        json={"email": "linkme@example.com", "intent": "link", "client": "android"},
        cookies={"asr_session": tok},
    )
    assert ok.status_code == 200
    assert "연결 링크" in ok.json()["message"]
    assert sent and "mobile=1" in sent[0]
    # Extract token and redeem as link
    import urllib.parse

    q = urllib.parse.urlparse(sent[0]).query
    t = urllib.parse.parse_qs(q)["t"][0]
    open_r = TestClient(app, follow_redirects=False).get(
        "/api/auth/email/magic/open",
        params={"t": t, "mobile": "1"},
    )
    assert open_r.status_code == 302
    loc = open_r.headers["location"]
    assert "asr_session=" in loc
    assert "auth=linked" in loc or "auth=magic" in loc
    # Primary now has email linked
    pub = aa.public_user_with_providers(primary)
    assert "email" in pub["providers"]
    assert "google" in pub["providers"]


def test_unlink_last_provider_blocked() -> None:
    u = aa.resolve_or_create(
        "google", "118234567890123456789", email="solo@x.com", name="S"
    )
    from sentence_reading.llm.auth_google import issue_session_token

    tok = issue_session_token(u)
    client = TestClient(app)
    r = client.post(
        "/api/auth/unlink",
        json={"provider": "google"},
        cookies={"asr_session": tok},
    )
    assert r.status_code == 400
    assert r.json()["error"] == "last_provider"
