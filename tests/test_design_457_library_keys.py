"""design/457 - library lists per device, and read-done marks with a title key."""

from __future__ import annotations

import datetime as dt

import pytest
from fastapi.testclient import TestClient

from sentence_reading.api.app import app
from sentence_reading.llm import auth_google as ag
from sentence_reading.llm import library_keys, reading_done
from sentence_reading.llm.auth_google import AuthUser

A = "118234567890123456021"
B = "118234567890123456022"
PHONE = "phoneDEV0000000001"
WEB = "webDEV000000000002"
H = "b" * 64
T = "low temperature vapor deposition synthesis of alloyed nanoparticles"


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setenv("ASR_AUTH_SECRET", "test-secret-library-keys-xxxxxxxx")
    monkeypatch.setenv("ASR_ACCESS_GATE", "0")
    monkeypatch.setattr(library_keys, "_use_gcs", lambda: False)
    monkeypatch.setattr(reading_done, "_use_gcs", lambda: False)
    library_keys.reset_memory_for_tests()
    reading_done.reset_memory_for_tests()
    yield TestClient(app)
    library_keys.reset_memory_for_tests()
    reading_done.reset_memory_for_tests()


def _cookie(uid: str) -> dict[str, str]:
    user = AuthUser(uid=uid, email=f"{uid[-4:]}@example.com", name="N", picture="")
    return {ag.COOKIE_NAME: ag.issue_session_token(user)}


def _now(minutes: int = 0) -> str:
    t = dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=minutes)
    return t.isoformat().replace("+00:00", "Z")


def test_each_device_keeps_its_own_list_and_a_newer_list_replaces_it(client):
    c = _cookie(A)
    r = client.put("/api/library-keys", json={"dev": PHONE, "at": _now(), "items": [{"c": "p1", "h": H, "t": T}]}, cookies=c)
    assert r.json()["applied"] is True
    client.put("/api/library-keys", json={"dev": WEB, "at": _now(), "items": [{"c": "w1"}]}, cookies=c)
    devices = client.get("/api/library-keys", cookies=c).json()["devices"]
    assert devices[PHONE]["items"] == [{"c": "p1", "h": H, "t": T}]
    assert devices[WEB]["items"] == [{"c": "w1"}]
    client.put("/api/library-keys", json={"dev": PHONE, "at": _now(1), "items": []}, cookies=c)
    assert client.get("/api/library-keys", cookies=c).json()["devices"][PHONE]["items"] == []
    r = client.put("/api/library-keys", json={"dev": PHONE, "at": _now(-5), "items": [{"c": "old"}]}, cookies=c)
    assert r.json()["applied"] is False


def test_accounts_and_signed_out_are_kept_apart(client):
    client.put("/api/library-keys", json={"dev": PHONE, "at": _now(), "items": [{"c": "p1"}]}, cookies=_cookie(A))
    assert client.get("/api/library-keys", cookies=_cookie(B)).json()["devices"] == {}
    assert client.get("/api/library-keys").status_code == 401


def test_bad_lists_are_refused(client):
    c = _cookie(A)
    for body in [
        {"dev": "x", "at": _now(), "items": []},
        {"dev": PHONE, "at": "soon", "items": []},
        {"dev": PHONE, "at": _now(), "items": [{"c": "bad id"}]},
        {"dev": PHONE, "at": _now(), "items": [{"c": "p1", "h": "XYZ"}]},
        {"dev": PHONE, "at": _now(), "items": [{"c": "p1", "t": " padded "}]},
        {"dev": PHONE, "at": _now(), "items": [{"c": "p1", "t": "x" * 301}]},
    ]:
        assert client.put("/api/library-keys", json=body, cookies=c).status_code == 400


def test_a_device_not_heard_from_for_long_is_left_out():
    store = library_keys._empty()
    now = dt.datetime(2026, 10, 26, tzinfo=dt.timezone.utc)
    old = (now - dt.timedelta(days=library_keys.STALE_DAYS + 1)).isoformat()
    library_keys._apply(store, PHONE, old, [{"c": "p1"}], now - dt.timedelta(days=library_keys.STALE_DAYS + 1))
    library_keys._apply(store, WEB, now.isoformat(), [{"c": "w1"}], now)
    assert set(store["devices"]) == {WEB}


def test_read_done_keeps_the_title_key_and_fills_it_in_later(client):
    c = _cookie(A)
    at = "2026-10-22T10:00:00Z"
    client.put("/api/read-done/abc123", json={"done": True, "at": at, "dev": PHONE, "h": H}, cookies=c)
    r = client.put("/api/read-done/abc123", json={"done": True, "at": at, "dev": WEB, "t": T}, cookies=c)
    assert r.json()["applied"] is True
    mark = client.get("/api/read-done", cookies=c).json()["marks"]["abc123"]
    assert mark == {"done": True, "at": at, "dev": PHONE, "h": H, "t": T}
    r = client.put("/api/read-done/abc123", json={"done": True, "at": at, "dev": WEB, "t": T}, cookies=c)
    assert r.json()["applied"] is False
    r = client.put("/api/read-done/abc123", json={"done": False, "at": at, "dev": WEB}, cookies=c)
    assert r.json()["applied"] is False
    bad = {"done": True, "at": at, "dev": PHONE, "t": ""}
    assert client.put("/api/read-done/abc123", json=bad, cookies=c).status_code == 400
