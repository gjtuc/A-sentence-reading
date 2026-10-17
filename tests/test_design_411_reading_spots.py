"""design/411 - live reading spots: numbers only, newer wins, per account."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from sentence_reading.api.app import app
from sentence_reading.llm import auth_google as ag
from sentence_reading.llm import reading_spots
from sentence_reading.llm.auth_google import AuthUser

ROOT = Path(__file__).resolve().parents[1]
A = "118234567890123456011"
B = "118234567890123456012"
PHONE = "phoneDEV0000000001"
WEB = "webDEV000000000002"


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setenv("ASR_AUTH_SECRET", "test-secret-reading-spots-xxxxxxx")
    monkeypatch.setenv("ASR_ACCESS_GATE", "0")
    monkeypatch.setattr(reading_spots, "_use_gcs", lambda: False)
    reading_spots.reset_memory_for_tests()
    yield TestClient(app)
    reading_spots.reset_memory_for_tests()


def _cookie(uid: str) -> dict[str, str]:
    user = AuthUser(uid=uid, email=f"{uid[-4:]}@example.com", name="N", picture="")
    return {ag.COOKIE_NAME: ag.issue_session_token(user)}


def _spot(si: int, fi: int, at: str, dev: str = PHONE) -> dict:
    return {"si": si, "fi": fi, "at": at, "dev": dev}


def test_put_then_since_returns_only_newer_changes(client):
    c = _cookie(A)
    r = client.put("/api/spots/abc123", json=_spot(4, 1, "2026-10-17T10:00:00.000Z"), cookies=c).json()
    assert r == {"ok": True, "rev": 1, "applied": True}
    r = client.put("/api/spots/def456", json=_spot(9, 0, "2026-10-17T10:00:05.000Z"), cookies=c).json()
    assert r["rev"] == 2
    page = client.get("/api/spots?since=0", cookies=c).json()
    assert page["rev"] == 2 and set(page["spots"]) == {"abc123", "def456"}
    assert page["spots"]["abc123"] == {**_spot(4, 1, "2026-10-17T10:00:00.000Z"), "rev": 1}
    page = client.get("/api/spots?since=1", cookies=c).json()
    assert set(page["spots"]) == {"def456"}
    assert client.get("/api/spots?since=2", cookies=c).json()["spots"] == {}


def test_an_older_spot_does_not_replace_a_newer_one(client):
    c = _cookie(A)
    client.put("/api/spots/abc123", json=_spot(10, 2, "2026-10-17T10:00:10.000Z"), cookies=c)
    r = client.put("/api/spots/abc123", json=_spot(3, 0, "2026-10-17T10:00:01.000Z", WEB), cookies=c).json()
    assert r["applied"] is False and r["rev"] == 1
    assert client.get("/api/spots", cookies=c).json()["spots"]["abc123"]["si"] == 10


def test_accounts_do_not_see_each_other(client):
    client.put("/api/spots/abc123", json=_spot(1, 0, "2026-10-17T10:00:00Z"), cookies=_cookie(A))
    assert client.get("/api/spots", cookies=_cookie(B)).json() == {"ok": True, "rev": 0, "spots": {}}


def test_bad_input_is_refused(client):
    c = _cookie(A)
    assert client.put("/api/spots/abc123", json=_spot(-1, 0, "2026-10-17T10:00:00Z"), cookies=c).status_code == 400
    assert client.put("/api/spots/abc123", json=_spot(1, 0, "yesterday"), cookies=c).status_code == 400
    assert client.put("/api/spots/abc123", json=_spot(1, 0, "2026-10-17T10:00:00Z", "x"), cookies=c).status_code == 400
    assert client.put("/api/spots/abc123", json={**_spot(1, 0, "2026-10-17T10:00:00Z"), "si": True}, cookies=c).status_code == 400
    assert client.put("/api/spots/a%20b", json=_spot(1, 0, "2026-10-17T10:00:00Z"), cookies=c).status_code == 400
    assert client.get("/api/spots").status_code == 401


def test_the_store_keeps_numbers_only_and_drops_the_oldest(client, monkeypatch):
    monkeypatch.setattr(reading_spots, "MAX_SPOTS", 3)
    c = _cookie(A)
    body = {**_spot(1, 0, "2026-10-17T10:00:00Z"), "title": "Secret paper", "text": "words"}
    for i in range(5):
        client.put(f"/api/spots/p{i}", json={**body, "at": f"2026-10-17T10:00:0{i}Z"}, cookies=c)
    spots = client.get("/api/spots", cookies=c).json()["spots"]
    assert set(spots) == {"p2", "p3", "p4"}
    assert all(set(v) == {"si", "fi", "at", "dev", "rev"} for v in spots.values())


def test_cas_retries_a_conflict_and_never_writes_without_the_generation(monkeypatch):
    calls: list[int] = []
    store = {"raw": None, "gen": 0}

    def fake_download(name, meter=True):
        return store["raw"], store["gen"]

    def fake_upload(name, data, *, if_generation_match, content_type, meter):
        calls.append(if_generation_match)
        if len(calls) == 1:
            store["gen"] = 7
            return "conflict"
        store["raw"], store["gen"] = data, store["gen"] + 1
        return "ok"

    monkeypatch.setattr(reading_spots, "_use_gcs", lambda: True)
    monkeypatch.setattr(reading_spots, "personal_object_name", lambda *p: "users/u/reading_spots/spots.json")
    monkeypatch.setattr(reading_spots, "download_bytes_generation", fake_download)
    monkeypatch.setattr(reading_spots, "upload_bytes_generation_match", fake_upload)
    status, rev = reading_spots.put("u", "abc", reading_spots.clean_spot(_spot(2, 1, "2026-10-17T10:00:00Z")))
    assert (status, rev) == ("ok", 1)
    assert calls == [0, 7]


def test_client_publishes_only_real_moves_and_follows_newer_spots():
    lib = (ROOT / "mobile/lib/state/library_controller.dart").read_text(encoding="utf-8")
    assert lib.count("await persistOpenedProgress(publish: true);") == 4
    assert "Future<void> persistOpenedProgress({bool publish = false, String? at})" in lib
    assert "await persistOpenedProgress(at: at);" in lib
    shell = (ROOT / "mobile/lib/screens/home_shell.dart").read_text(encoding="utf-8")
    assert "widget.library.startSpotSync();" in shell and "widget.library.stopSpotSync();" in shell
    kinds_py = (ROOT / "src/sentence_reading/llm/evidence_kinds.py").read_text(encoding="utf-8")
    kinds_dart = (ROOT / "mobile/lib/services/evidence_kinds.dart").read_text(encoding="utf-8")
    for k in ("spot_follow", "spot_sync_failed"):
        assert f'"{k}"' in kinds_py and f"'{k}'" in kinds_dart