"""Flutter mobile email auth contract (0.2.86 · design/33 · design/61)."""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from sentence_reading.api.app import app
from sentence_reading.llm import auth_accounts as aa
from sentence_reading.llm import auth_google as ag

ROOT = Path(__file__).resolve().parents[1]
MOBILE = ROOT / "mobile"
DESIGN = ROOT / "docs" / "design" / "61-mobile-email-auth.md"


@pytest.fixture(autouse=True)
def _iso(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.setenv("ASR_EMAIL_AUTH", "1")
    monkeypatch.delenv("ASR_GOOGLE_CLIENT_ID", raising=False)
    monkeypatch.delenv("ASR_KAKAO_REST_API_KEY", raising=False)
    monkeypatch.setenv("ASR_AUTH_SECRET", "mobile-email-auth-test-secret")
    root = tmp_path / "proj"
    root.mkdir()
    (root / "pyproject.toml").write_text("[project]\nname='t'\n", encoding="utf-8")
    monkeypatch.setattr(aa, "project_root", lambda: root)
    monkeypatch.setattr(aa, "accounts_path", lambda: root / "data" / "auth" / "accounts.json")
    ag.reset_gcs_uid()
    yield
    ag.reset_gcs_uid()


def test_status_mobile_email_auth_flag() -> None:
    with TestClient(app) as client:
        st = client.get("/api/status").json()
    assert st["version"] == "0.2.86"
    assert st["mobile_email_auth"] is True
    assert st["mobile_flutter_scaffold"] is True
    assert st["mobile_android_platform"] is True
    # Live Enable / IPS belong to Trading Gate — never on ASR status
    assert "live_enable" not in st
    assert "ips" not in st


def test_email_login_sets_session_cookie() -> None:
    client = TestClient(app)
    r = client.post(
        "/api/auth/email/register",
        json={"email": "m@example.com", "password": "password1", "name": "M"},
    )
    assert r.status_code == 200
    assert "asr_session" in r.cookies
    uid = r.json()["user"]["uid"]
    client.post("/api/auth/logout")
    # EDGE: bad credentials
    bad = client.post(
        "/api/auth/email/login",
        json={"email": "m@example.com", "password": "wrong-password"},
    )
    assert bad.status_code == 401
    # EDGE: empty / nonsense email
    weird = client.post(
        "/api/auth/email/login",
        json={"email": "not-an-email", "password": "password1"},
    )
    assert weird.status_code in (400, 401)
    ok = client.post(
        "/api/auth/email/login",
        json={"email": "m@example.com", "password": "password1"},
    )
    assert ok.status_code == 200
    assert ok.json()["user"]["uid"] == uid
    assert "asr_session" in ok.cookies
    st = client.get("/api/auth/status").json()
    assert st["user"]["uid"] == uid


def test_mobile_dart_auth_sources() -> None:
    pub = (MOBILE / "pubspec.yaml").read_text(encoding="utf-8")
    assert "0.2.86" in pub
    assert "shared_preferences:" in pub
    client = (MOBILE / "lib" / "api" / "client.dart").read_text(encoding="utf-8")
    assert "/api/auth/email/login" in client
    assert "/api/auth/email/register" in client
    assert "/api/auth/logout" in client
    assert "parseAsrSessionCookie" in client or "session_store" in client
    store = (MOBILE / "lib" / "api" / "session_store.dart").read_text(encoding="utf-8")
    assert "asr_session" in store
    assert "parseAsrSessionCookie" in store
    login = (MOBILE / "lib" / "screens" / "login_screen.dart").read_text(encoding="utf-8")
    assert "loginEmail" in login
    assert "registerEmail" in login
    # WHY: login UI must not expose infra / Trading Gate jargon to users.
    assert "Live Enable" not in login
    assert "Trading Gate" not in login
    assert "Cloud Run" not in login
    login = (MOBILE / "lib" / "screens" / "login_screen.dart").read_text(encoding="utf-8")
    assert "비밀번호 확인" in login
    assert "visibility" in login
    assert "validateRegisterPasswords" in login
    assert DESIGN.is_file()
    design = DESIGN.read_text(encoding="utf-8")
    assert "0.2.86" in design
    assert "Trading Gate" in design or "ASR 밖" in design


def test_no_secrets_in_mobile_dart() -> None:
    banned = re.compile(
        r"(AIza[0-9A-Za-z_-]{20,}|BEGIN (RSA |EC )?PRIVATE KEY|"
        r"GEMINI_API_KEY|GOOGLE_APPLICATION_CREDENTIALS|"
        r"client_secret|private_key)",
        re.I,
    )
    for path in MOBILE.rglob("*.dart"):
        if "build" in path.parts or ".dart_tool" in path.parts:
            continue
        text = path.read_text(encoding="utf-8")
        assert banned.search(text) is None, f"secret-like pattern in {path}"


def test_html_asset_bust_tracks_app_version() -> None:
    with TestClient(app) as client:
        html = client.get("/").text
    assert "app.js?v=0.2.86" in html
    assert "styles.css?v=0.2.86" in html
