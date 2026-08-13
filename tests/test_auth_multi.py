"""멀티 로그인 · 계정 연결 (0.2.24)."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from sentence_reading.api.app import app
from sentence_reading.llm import auth_accounts as aa
from sentence_reading.llm import auth_google as ag
from sentence_reading.llm.auth_google import AuthUser


@pytest.fixture(autouse=True)
def _iso(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.setenv("ASR_EMAIL_AUTH", "1")
    monkeypatch.delenv("ASR_GOOGLE_CLIENT_ID", raising=False)
    monkeypatch.delenv("ASR_KAKAO_REST_API_KEY", raising=False)
    monkeypatch.setenv("ASR_AUTH_SECRET", "multi-auth-test-secret")
    root = tmp_path / "proj"
    root.mkdir()
    (root / "pyproject.toml").write_text("[project]\nname='t'\n", encoding="utf-8")
    monkeypatch.setattr(aa, "project_root", lambda: root)
    monkeypatch.setattr(aa, "accounts_path", lambda: root / "data" / "auth" / "accounts.json")
    ag.reset_gcs_uid()
    yield
    ag.reset_gcs_uid()


def test_status_version() -> None:
    client = TestClient(app)
    st = client.get("/api/status").json()
    assert st["version"] == "0.3.43"
    assert st["auth"]["providers"]["email"] is True


def test_email_register_login_link_google(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ASR_GOOGLE_CLIENT_ID", "cid.apps.googleusercontent.com")

    def fake_verify(cred: str) -> AuthUser:
        return AuthUser(uid="118234567890123456789", email="g@x.com", name="G")

    monkeypatch.setattr("sentence_reading.api.app.verify_google_id_token", fake_verify)
    client = TestClient(app)
    r = client.post(
        "/api/auth/email/register",
        json={"email": "a@example.com", "password": "password1", "name": "A"},
    )
    assert r.status_code == 200
    uid = r.json()["user"]["uid"]
    assert "email" in r.json()["user"]["providers"]

    client.post("/api/auth/logout")
    r2 = client.post(
        "/api/auth/email/login",
        json={"email": "a@example.com", "password": "password1"},
    )
    assert r2.status_code == 200
    assert r2.json()["user"]["uid"] == uid

    r3 = client.post(
        "/api/auth/google",
        json={"credential": "jwt", "mode": "link"},
    )
    assert r3.status_code == 200
    providers = r3.json()["user"]["providers"]
    assert "email" in providers and "google" in providers
    assert r3.json()["user"]["uid"] == uid


def test_link_conflict(monkeypatch: pytest.MonkeyPatch) -> None:
    u1 = aa.resolve_or_create(
        "email", "one@example.com", email="one@example.com", password="password1"
    )
    aa.resolve_or_create(
        "email", "two@example.com", email="two@example.com", password="password1"
    )
    with pytest.raises(ValueError, match="conflict"):
        aa.link_provider(u1.uid, "email", "two@example.com", password="password1")


def test_ui_multi_auth() -> None:
    root = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "sentence_reading"
        / "static"
    )
    html = (root / "index.html").read_text(encoding="utf-8")
    assert "카카오로 계속하기" in html
    assert "구글로 계속하기" in html
    assert "이메일로 계속하기" in html
    assert "authDialog" in html
    js = (root / "app.js").read_text(encoding="utf-8")
    assert "openAuthDialog" in js
    assert "/api/auth/email/magic/request" in js
    assert "requestEmailMagicLink" in js
    assert "authAccountBtn" in js
    assert "authPasswordInput" not in html
    assert "authEmailRegisterBtn" not in html
    assert "/api/auth/email/login" not in js


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
