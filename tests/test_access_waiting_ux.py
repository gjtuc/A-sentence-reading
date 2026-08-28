# -*- coding: utf-8 -*-
"""design/84 — access waiting UX (waiting shell after login)."""
from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from sentence_reading.api.app import app
from sentence_reading.llm import access_gate as ag
from sentence_reading.llm import auth_accounts as aa
from sentence_reading.llm import auth_google as agu


@pytest.fixture(autouse=True)
def _iso(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.setenv("ASR_ACCESS_GATE", "1")
    monkeypatch.setenv("ASR_ADMIN_EMAILS", "admin@example.com")
    monkeypatch.setenv("ASR_AUTH_SECRET", "access-wait-test-secret")
    monkeypatch.setenv("ASR_EMAIL_AUTH", "1")
    monkeypatch.setenv("ASR_EMAIL_PASSWORD", "1")
    monkeypatch.setenv("ASR_LOGIN_REQUIRED", "0")
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


def test_status_waiting_flags() -> None:
    with TestClient(app) as client:
        st = client.get("/api/status").json()
    assert st["version"] == "0.3.78"
    assert st["access_waiting_ux"] is True
    assert st["mobile_access_waiting_ux"] is True
    assert st["access_gate_enabled"] is True


def test_pending_cannot_use_paid() -> None:
    client = TestClient(app)
    _login_admin(client)
    code = client.post("/api/access/admin/mint", json={}).json()["code"]
    client.post("/api/auth/logout")
    _login_user(client)
    red = client.post("/api/access/invite", json={"code": code})
    assert red.status_code == 200
    assert red.json()["access"]["status"] == "pending"
    assert red.json()["access"]["can_use_paid"] is False
    st = client.get("/api/access/status").json()
    assert st["can_use_paid"] is False


def test_denied_reenter_to_pending() -> None:
    client = TestClient(app)
    _login_admin(client)
    code1 = client.post("/api/access/admin/mint", json={}).json()["code"]
    client.post("/api/auth/logout")
    uid = _login_user(client, email="deny@example.com")
    assert client.post("/api/access/invite", json={"code": code1}).status_code == 200
    client.post("/api/auth/logout")
    _login_admin(client)
    dec = client.post(
        "/api/access/admin/decide",
        json={"uid": uid, "decision": "deny"},
    )
    assert dec.status_code == 200, dec.text
    code2 = client.post("/api/access/admin/mint", json={}).json()["code"]
    client.post("/api/auth/logout")
    # same user login again
    r = client.post(
        "/api/auth/email/login",
        json={"email": "deny@example.com", "password": "password1"},
    )
    assert r.status_code == 200
    denied = client.get("/api/access/status").json()
    assert denied["status"] == "denied"
    assert denied["can_use_paid"] is False
    # Product: deny == waiting — re-enter new code → pending
    red = client.post("/api/access/invite", json={"code": code2})
    assert red.status_code == 200
    assert red.json()["access"]["status"] == "pending"
    assert red.json()["access"]["can_use_paid"] is False


def test_allow_unlocks_paid() -> None:
    client = TestClient(app)
    _login_admin(client)
    code = client.post("/api/access/admin/mint", json={}).json()["code"]
    client.post("/api/auth/logout")
    uid = _login_user(client, email="ok@example.com")
    assert client.post("/api/access/invite", json={"code": code}).status_code == 200
    client.post("/api/auth/logout")
    _login_admin(client)
    assert (
        client.post(
            "/api/access/admin/decide",
            json={"uid": uid, "decision": "allow"},
        ).status_code
        == 200
    )
    client.post("/api/auth/logout")
    assert (
        client.post(
            "/api/auth/email/login",
            json={"email": "ok@example.com", "password": "password1"},
        ).status_code
        == 200
    )
    st = client.get("/api/access/status").json()
    assert st["can_use_paid"] is True


def test_gate_off_skips_wait(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ASR_ACCESS_GATE", "0")
    client = TestClient(app)
    _login_user(client, email="open@example.com")
    st = client.get("/api/access/status").json()
    assert st["gate_enabled"] is False
    assert st["can_use_paid"] is True


def test_web_and_mobile_waiting_hooks() -> None:
    root = Path(__file__).resolve().parents[1]
    js = (root / "src" / "sentence_reading" / "static" / "app.js").read_text(
        encoding="utf-8"
    )
    html = (root / "src" / "sentence_reading" / "static" / "index.html").read_text(
        encoding="utf-8"
    )
    css = (root / "src" / "sentence_reading" / "static" / "styles.css").read_text(
        encoding="utf-8"
    )
    assert "accessWaitingPanel" in html
    assert "enterAppOrAccessWait" in js
    assert "asr-access-waiting" in css
    shell = (root / "mobile" / "lib" / "screens" / "home_shell.dart").read_text(
        encoding="utf-8"
    )
    wait = (
        root / "mobile" / "lib" / "screens" / "access_waiting_screen.dart"
    ).read_text(encoding="utf-8")
    assert "AccessWaitingScreen" in shell
    assert "onUnlocked" in wait
    assert "Timer.periodic" in wait
