"""Access gate OTP invite + TTL/rate-limit (0.3.3 · design/67)."""

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
    monkeypatch.setenv("ASR_INVITE_TTL_HOURS", "48")
    monkeypatch.setenv("ASR_INVITE_REDEEM_MAX", "20")
    monkeypatch.setenv("ASR_INVITE_REDEEM_WINDOW_SEC", "900")
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
    assert st["version"] == "0.3.12"
    assert st.get("mobile_invite_copy_minimal") is True
    assert st.get("mobile_admin_emails_configured") is True
    assert st.get("mobile_invite_redeem_e2e") is True
    assert st.get("mobile_access_session_clear") is True
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
    assert "0.3.12" in pub
    client = (mobile / "lib" / "api" / "client.dart").read_text(encoding="utf-8")
    assert "redeemInviteCode" in client and "mintInviteCode" in client
    settings = (mobile / "lib" / "screens" / "settings_screen.dart").read_text(
        encoding="utf-8"
    )
    assert "Allow" in settings and "Deny" in settings
    assert "isAdmin" in settings or "access?.isAdmin" in settings
    assert "관리자에게 부여받은 OTP" in settings
    assert "addListener" in settings and "_onAuthChanged" in settings
    assert "서버가 만든" not in settings
    assert "TqG3" not in settings
    assert "XXXX-XXXX" not in settings
    design = (
        Path(__file__).resolve().parents[1] / "docs" / "design" / "67-access-gate.md"
    )
    assert design.is_file()
    assert "0.3.3" in design.read_text(encoding="utf-8")


def test_invite_expires(monkeypatch: pytest.MonkeyPatch) -> None:
    """EDGE: past expires_at → 409 code_expired; not redeemable."""
    monkeypatch.setenv("ASR_INVITE_TTL_HOURS", "1")  # 1 hour
    client = TestClient(app)
    _login_admin(client)
    minted = client.post("/api/access/admin/mint", json={}).json()
    code = minted["code"]
    assert minted.get("expires_at")
    # rewind expires_at on disk
    store = ag._read_invites()
    for row in store["codes"]:
        if row.get("status") == "open":
            row["expires_at"] = int(row["created_at"]) - 10
    ag._write_invites(store)
    client.post("/api/auth/logout")
    _login_user(client)
    expired = client.post("/api/access/invite", json={"code": code})
    assert expired.status_code == 409
    assert expired.json()["error"] == "code_expired"


def test_redeem_rate_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    """EDGE: too many wrong guesses → 429 rate_limited."""
    monkeypatch.setenv("ASR_INVITE_REDEEM_MAX", "3")
    monkeypatch.setenv("ASR_INVITE_REDEEM_WINDOW_SEC", "900")
    client = TestClient(app)
    _login_user(client)
    last = None
    for i in range(3):
        last = client.post("/api/access/invite", json={"code": f"AAAA-BBB{i}"})
        assert last.status_code == 403, last.text
    blocked = client.post("/api/access/invite", json={"code": "ZZZZ-YYYY"})
    assert blocked.status_code == 429
    assert blocked.json()["error"] == "rate_limited"


def test_ttl_env_edges(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ASR_INVITE_TTL_HOURS", "0")
    assert ag.invite_ttl_seconds() == 0
    monkeypatch.setenv("ASR_INVITE_TTL_HOURS", "-3")
    assert ag.invite_ttl_seconds() == 48 * 3600
    monkeypatch.setenv("ASR_INVITE_TTL_HOURS", "nope")
    assert ag.invite_ttl_seconds() == 48 * 3600
    monkeypatch.setenv("ASR_INVITE_REDEEM_MAX", "0")
    assert ag.redeem_max_attempts() == 10
    monkeypatch.setenv("ASR_INVITE_REDEEM_WINDOW_SEC", "abc")
    assert ag.redeem_window_seconds() == 900


def test_status_exposes_ttl_flags() -> None:
    with TestClient(app) as client:
        st = client.get("/api/status").json()
    assert st["version"] == "0.3.12"
    assert st["access_invite_ttl_seconds"] == 48 * 3600
    assert st["access_redeem_max"] >= 1
    assert "live_enable" not in st
    assert "ips" not in st


def test_access_status_is_admin_flag() -> None:
    client = TestClient(app)
    _login_user(client)
    st = client.get("/api/access/status").json()
    assert st.get("is_admin") is False
    client.post("/api/auth/logout")
    _login_admin(client)
    st2 = client.get("/api/access/status").json()
    assert st2.get("is_admin") is True
    assert "live_enable" not in client.get("/api/status").json()


def test_settings_clears_mint_on_logout() -> None:
    """MULTI-USER: Settings must wipe minted OTP + typed code when logged out."""
    src = Path(__file__).resolve().parents[1] / "mobile/lib/screens/settings_screen.dart"
    text = src.read_text(encoding="utf-8")
    assert "_minted = null" in text
    assert "_code.clear()" in text
    assert "IndexedStack" in text or "next account" in text or "다음 계정" in text or "leftover _minted" in text


def test_settings_allow_not_blocked_by_reload() -> None:
    """MULTI-USER: Allow/Deny must not disable solely because _loading refresh is true."""
    src = Path(__file__).resolve().parents[1] / "mobile/lib/screens/settings_screen.dart"
    text = src.read_text(encoding="utf-8")
    assert "bool _mutating" in text
    assert "_mutating" in text
    assert "onPressed: _mutating" in text
