"""design/130 — cloud error logs API + redact + authz."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from sentence_reading.api.app import app
from sentence_reading.llm import error_logs as errlog
from sentence_reading.llm.auth_google import AuthUser, issue_session_token, COOKIE_NAME

ROOT = Path(__file__).resolve().parents[1]
DESIGN = ROOT / "docs" / "design" / "130-cloud-error-logs.md"


@pytest.fixture()
def err_tmp(tmp_path, monkeypatch):
    monkeypatch.setenv("ASR_CLOUD_ERROR_LOGS", "1")
    monkeypatch.setenv("ASR_LOGIN_REQUIRED", "0")
    monkeypatch.setenv("ASR_ACCESS_GATE", "0")
    monkeypatch.setenv("ASR_ADMIN_EMAILS", "admin@example.com")
    monkeypatch.setattr(errlog, "local_events_path", lambda: tmp_path / "events.jsonl")
    monkeypatch.setattr(errlog, "local_seen_path", lambda: tmp_path / "admin_seen.json")
    monkeypatch.setattr(errlog, "_gcs_events_object", lambda: None)
    monkeypatch.setattr(errlog, "_gcs_seen_object", lambda: None)
    errlog._REPORT_MEM.clear()
    return tmp_path


def _cookie(email: str, uid: str = "u1") -> dict[str, str]:
    user = AuthUser(uid=uid, email=email, name="t", picture="")
    tok = issue_session_token(user)
    return {COOKIE_NAME: tok}


def test_design_and_status_pin(err_tmp):
    assert DESIGN.is_file()
    st = TestClient(app).get("/api/status").json()
    assert st["version"] == "0.3.60"
    assert st.get("cloud_error_logs") is True
    assert st.get("mobile_cloud_error_logs") is True


def test_redact_secrets():
    s = errlog.redact_text(
        "Authorization: Bearer abc.def password=sekrit cookie=c1",
        limit=500,
    )
    assert "abc.def" not in s
    assert "sekrit" not in s
    assert "REDACTED" in s


def test_report_requires_auth(err_tmp):
    c = TestClient(app)
    r = c.post("/api/errors/report", json={"kind": "test", "message": "x"})
    assert r.status_code == 401


def test_report_and_admin_list_isolation(err_tmp):
    c = TestClient(app)
    # User A reports
    r = c.post(
        "/api/errors/report",
        json={
            "kind": "hang",
            "message": "open stuck Authorization: Bearer tokensecret",
            "paper_title": "Ewbank paper",
            "cache_id": "abcd1234ef",
            "user_id": "attacker",  # MUST be ignored
        },
        cookies=_cookie("user@example.com", uid="user_a"),
    )
    assert r.status_code == 200, r.text
    eid = r.json()["id"]

    # Non-admin cannot list
    denied = c.get(
        "/api/errors/admin",
        cookies=_cookie("user@example.com", uid="user_a"),
    )
    assert denied.status_code == 403

    # Admin sees event (other user's) with redaction + session uid
    admin = c.get(
        "/api/errors/admin",
        cookies=_cookie("admin@example.com", uid="admin1"),
    )
    assert admin.status_code == 200, admin.text
    events = admin.json()["events"]
    assert events
    hit = next(e for e in events if e["id"] == eid)
    assert hit["uid"] == "user_a"
    assert hit["paper_title"].startswith("Ewbank")
    assert hit["cache_id"] == "abcd1234ef"
    assert "tokensecret" not in hit["message"]
    assert "REDACTED" in hit["message"]


def test_badge_and_seen(err_tmp):
    c = TestClient(app)
    c.post(
        "/api/errors/report",
        json={"kind": "crash", "message": "boom"},
        cookies=_cookie("user@example.com", uid="user_b"),
    )
    badge = c.get(
        "/api/errors/admin/badge",
        cookies=_cookie("admin@example.com", uid="admin1"),
    )
    assert badge.status_code == 200
    assert badge.json()["count"] >= 1
    seen = c.post(
        "/api/errors/admin/seen",
        cookies=_cookie("admin@example.com", uid="admin1"),
    )
    assert seen.status_code == 200
    badge2 = c.get(
        "/api/errors/admin/badge",
        cookies=_cookie("admin@example.com", uid="admin1"),
    )
    assert badge2.json()["count"] == 0


def test_kill_switch(err_tmp, monkeypatch):
    monkeypatch.setenv("ASR_CLOUD_ERROR_LOGS", "0")
    c = TestClient(app)
    st = c.get("/api/status").json()
    assert st["cloud_error_logs"] is False
    r = c.post(
        "/api/errors/report",
        json={"kind": "x", "message": "y"},
        cookies=_cookie("user@example.com"),
    )
    assert r.status_code == 503


def test_reject_traversal_cache_id(err_tmp):
    ev = errlog.normalize_event(
        {
            "kind": "x",
            "message": "m",
            "cache_id": "../etc/passwd",
        },
        uid="u1",
        email="a@b.c",
    )
    assert ev is not None
    assert ev["cache_id"] == ""


def test_rate_limit(err_tmp, monkeypatch):
    monkeypatch.setenv("ASR_ERROR_REPORT_MAX", "3")
    monkeypatch.setenv("ASR_ERROR_REPORT_WINDOW_SEC", "600")
    errlog._REPORT_MEM.clear()
    c = TestClient(app)
    cookies = _cookie("user@example.com", uid="rate_u")
    codes = []
    for i in range(5):
        r = c.post(
            "/api/errors/report",
            json={"kind": "spam", "message": f"m{i}"},
            cookies=cookies,
        )
        codes.append(r.status_code)
    assert codes.count(200) == 3
    assert 429 in codes
