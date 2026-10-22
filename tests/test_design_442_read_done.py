"""design/442 - papers marked as read to the end: per account, newer wins, hash kept."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from sentence_reading.api.app import app
from sentence_reading.llm import auth_google as ag
from sentence_reading.llm import reading_done
from sentence_reading.llm.auth_google import AuthUser

A = "118234567890123456011"
B = "118234567890123456012"
PHONE = "phoneDEV0000000001"
WEB = "webDEV000000000002"
H = "a" * 64


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setenv("ASR_AUTH_SECRET", "test-secret-reading-done-xxxxxxxx")
    monkeypatch.setenv("ASR_ACCESS_GATE", "0")
    monkeypatch.setattr(reading_done, "_use_gcs", lambda: False)
    reading_done.reset_memory_for_tests()
    yield TestClient(app)
    reading_done.reset_memory_for_tests()


def _cookie(uid: str) -> dict[str, str]:
    user = AuthUser(uid=uid, email=f"{uid[-4:]}@example.com", name="N", picture="")
    return {ag.COOKIE_NAME: ag.issue_session_token(user)}


def _mark(done: bool, at: str, dev: str = PHONE, h: str | None = H) -> dict:
    out = {"done": done, "at": at, "dev": dev}
    if h is not None:
        out["h"] = h
    return out


def test_a_mark_is_kept_with_its_hash(client):
    c = _cookie(A)
    r = client.put("/api/read-done/abc123", json=_mark(True, "2026-10-22T10:00:00.000Z"), cookies=c)
    assert r.json() == {"ok": True, "rev": 1, "applied": True}
    page = client.get("/api/read-done", cookies=c).json()
    assert page["rev"] == 1
    assert page["marks"] == {"abc123": _mark(True, "2026-10-22T10:00:00.000Z")}


def test_un_marking_later_wins_and_an_older_write_does_not(client):
    c = _cookie(A)
    client.put("/api/read-done/abc123", json=_mark(True, "2026-10-22T10:00:00Z"), cookies=c)
    r = client.put("/api/read-done/abc123", json=_mark(False, "2026-10-22T10:05:00Z", WEB), cookies=c)
    assert r.json()["applied"] is True
    r = client.put("/api/read-done/abc123", json=_mark(True, "2026-10-22T10:01:00Z"), cookies=c)
    assert r.json()["applied"] is False
    assert client.get("/api/read-done", cookies=c).json()["marks"]["abc123"]["done"] is False


def test_accounts_do_not_see_each_other(client):
    client.put("/api/read-done/abc123", json=_mark(True, "2026-10-22T10:00:00Z"), cookies=_cookie(A))
    assert client.get("/api/read-done", cookies=_cookie(B)).json() == {
        "ok": True,
        "rev": 0,
        "marks": {},
    }


def test_bad_input_is_refused(client):
    c = _cookie(A)
    bad = [
        {"done": "yes", "at": "2026-10-22T10:00:00Z", "dev": PHONE},
        {"done": True, "at": "yesterday", "dev": PHONE},
        {"done": True, "at": "2026-10-22T10:00:00Z", "dev": "x"},
        _mark(True, "2026-10-22T10:00:00Z", h="XYZ"),
        _mark(True, "2026-10-22T10:00:00Z", h="A" * 64),
    ]
    for body in bad:
        assert client.put("/api/read-done/abc123", json=body, cookies=c).status_code == 400
    assert client.put("/api/read-done/bad id", json=_mark(True, "2026-10-22T10:00:00Z"), cookies=c).status_code == 400


def test_a_mark_without_a_hash_is_kept(client):
    c = _cookie(A)
    client.put("/api/read-done/abc123", json=_mark(True, "2026-10-22T10:00:00Z", h=None), cookies=c)
    assert "h" not in client.get("/api/read-done", cookies=c).json()["marks"]["abc123"]


def test_signed_out_is_refused(client):
    assert client.get("/api/read-done").status_code == 401
    assert client.put("/api/read-done/abc123", json=_mark(True, "2026-10-22T10:00:00Z")).status_code == 401


def test_past_the_cap_the_oldest_mark_goes(monkeypatch):
    monkeypatch.setattr(reading_done, "MAX_MARKS", 2)
    store = {"version": 1, "rev": 0, "marks": {}}
    reading_done._apply(store, "p1", _mark(True, "2026-10-22T10:00:01Z"))
    reading_done._apply(store, "p2", _mark(True, "2026-10-22T10:00:03Z"))
    reading_done._apply(store, "p3", _mark(True, "2026-10-22T10:00:02Z"))
    assert set(store["marks"]) == {"p2", "p3"}
