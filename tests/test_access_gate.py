"""Access gate OTP invite + admin allow/deny (0.2.75 · design/67)."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from sentence_reading.api.app import app
from sentence_reading.llm import access_gate as ag
from sentence_reading.llm import auth_accounts as aa
from sentence_reading.llm import auth_google as agu
from sentence_reading.llm.auth_google import AuthUser, issue_session_token


@pytest.fixture(autouse=True)
def _iso(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.setenv("ASR_ACCESS_GATE", "1")
    monkeypatch.setenv("ASR_ADMIN_EMAILS", "admin@example.com")
    monkeypatch.setenv("ASR_AUTH_SECRET", "access-gate-test-secret")
    monkeypatch.setenv("ASR_EMAIL_AUTH", "1")
    root = tmp_path / "proj"
    root.mkdir()
    (root / "pyproject.toml").write_text("[project]\nname='t'\n", encoding="utf-8")
    monkeypatch.setattr(aa, "project_root", lambda: root)
    monkeypatch.setattr(aa, "accounts_path", lambda: root / "data" / "auth" / "accounts.json")
    monkeypatch.setattr(ag, "project_root", lambda: root)
    from sentence_reading.cache import paper_cache as pc

    monkeypatch.setattr(pc, "project_root", lambda: root)
    agu.reset_gcs_uid()
    yield
    agu.reset_gcs_uid()


def _login_admin(client: TestClient) -> None:
    r = client.post(
        "/api/auth/email/register",
        json={"email": "admin@example.com", "password": "password1", "name": "Ad"},
    )
    if r.status_code != 200:
        r = client.post(
            "/api/auth/email/login",
            json={"email": "admin@example.com", "password": "password1"},
        )
    assert r.status_code == 200, r.text


def _login_user(client: TestClient, email: str = "user@example.com") -> str:
    r = client.post(
        "/api/auth/email/register",
        json={"email": email, "password": "password1", "name": "U"},
    )
    if r.status_code != 200:
        r = client.post(
            "/api/auth/email/login",
            json={"email": email, "password": "password1"},
        )
    assert r.status_code == 200, r.text
    return r.json()["user"]["uid"]


def test_status_access_gate_flag() -> None:
    with TestClient(app) as client:
        st = client.get("/api/status").json()
    assert st["version"] == "0.2.75"
    assert st["access_gate"] is True
    assert st["mobile_access_gate"] is True
    assert "live_enable" not in st
    assert "ips" not in st


def test_generate_format_and_normalize() -> None:
    code = ag.generate_invite_code()
    assert len(code) == 9 and code[4] == "-"
    assert ag.normalize_invite_code("tq g3-v12t") == "TQG3V12T"
    assert len(ag.normalize_invite_code(code)) == 8
    assert ag.hash_invite_code("AbCd-EfGh") == ag.hash_invite_code("abcdefgh")


def test_mint_redeem_allow_paid_flow() -> None:
    client = TestClient(app)
    _login_admin(client)
    minted = client.post("/api/access/admin/mint", json={})
    assert minted.status_code == 200
    code = minted.json()["code"]
    assert "-" in code

    client.post("/api/auth/logout")
    uid = _login_user(client)

    # paid blocked before redeem
    denied = client.post("/api/tts", json={"text": "hello world"})
    # may be 403 access or 503 tts — but not 200 without allow when gate on
    assert denied.status_code in (403, 503)
    if denied.status_code == 403:
        assert denied.json()["error"] == "access_denied"

    ok = client.post("/api/access/invite", json={"code": code})
    assert ok.status_code == 200
    assert ok.json()["access"]["status"] == "pending"

    # reuse fails
    client.post("/api/auth/logout")
    _login_user(client, email="other@example.com")
    reused = client.post("/api/access/invite", json={"code": code})
    assert reused.status_code == 409

    # admin allow original user
    client.post("/api/auth/logout")
    _login_admin(client)
    pending = client.get("/api/access/admin/pending").json()["pending"]
    assert any(p["uid"] == uid for p in pending)
    decided = client.post(
        "/api/access/admin/decide",
        json={"uid": uid, "decision": "allow"},
    )
    assert decided.status_code == 200
    assert decided.json()["access"]["status"] == "allowed"

    events = client.get("/api/access/admin/notifications").json()["events"]
    types = {e.get("type") for e in events}
    assert "invite_pending" in types or "invite_minted" in types


def test_bad_code_edges() -> None:
    client = TestClient(app)
    _login_user(client)
    empty = client.post("/api/access/invite", json={"code": "   "})
    assert empty.status_code == 400
    short = client.post("/api/access/invite", json={"code": "AB"})
    assert short.status_code == 403
    bogus = client.post("/api/access/invite", json={"code": "AAAA-BBBB"})
    assert bogus.status_code == 403


def test_gate_off_allows() -> None:
    # monkeypatch env inside test via access_gate_enabled
    import os

    os.environ["ASR_ACCESS_GATE"] = "0"
    try:
        assert ag.access_gate_enabled() is False
        assert ag.user_may_use_paid("anyuid123456", is_admin=False) is True
    finally:
        os.environ["ASR_ACCESS_GATE"] = "1"


def test_mobile_sources() -> None:
    mobile = Path(__file__).resolve().parents[1] / "mobile"
    pub = (mobile / "pubspec.yaml").read_text(encoding="utf-8")
    assert "0.2.75" in pub
    client = (mobile / "lib" / "api" / "client.dart").read_text(encoding="utf-8")
    assert "redeemInviteCode" in client and "mintInviteCode" in client
    settings = (mobile / "lib" / "screens" / "settings_screen.dart").read_text(
        encoding="utf-8"
    )
    assert "Allow" in settings and "Deny" in settings
    assert "TqG3" in settings or "XXXX-XXXX" in settings
    design = (
        Path(__file__).resolve().parents[1] / "docs" / "design" / "67-access-gate.md"
    )
    assert design.is_file()
    assert "0.2.75" in design.read_text(encoding="utf-8")
