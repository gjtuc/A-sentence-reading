"""design/410 — near-sync links: only session descriptions pass the server."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from sentence_reading.api.app import app
from sentence_reading.llm import auth_google as ag
from sentence_reading.llm import near_links
from sentence_reading.llm.auth_google import AuthUser

OFFER = {"type": "offer", "sdp": "v=0\r\no=- 1 2 IN IP4 127.0.0.1\r\n"}
ANSWER = {"type": "answer", "sdp": "v=0\r\no=- 3 4 IN IP4 127.0.0.1\r\n"}


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setenv("ASR_AUTH_SECRET", "test-secret-near-links-xxxxxxxxxx")
    monkeypatch.setenv("ASR_ACCESS_GATE", "0")
    monkeypatch.setattr(near_links, "_use_gcs", lambda: False)
    near_links.reset_memory_for_tests()
    yield TestClient(app)
    near_links.reset_memory_for_tests()


def _cookie(uid: str) -> dict[str, str]:
    user = AuthUser(uid=uid, email=f"{uid[-4:]}@example.com", name="N", picture="")
    return {ag.COOKIE_NAME: ag.issue_session_token(user)}


A = "118234567890123456001"
B = "118234567890123456002"


def test_host_join_round_trip(client):
    host = _cookie(A)
    made = client.post("/api/near/links", json={"offer": OFFER}, cookies=host).json()
    assert made["ok"] is True
    link_id = made["link_id"]
    assert near_links.valid_link_id(link_id)
    assert made["expires_in"] == near_links.LINK_LIFE_S

    peek = client.get(f"/api/near/links/{link_id}", cookies=host).json()
    assert peek == {"ok": True, "claimed": False, "answer": None}

    joined = client.post("/api/near/links/claim", cookies=_cookie(A)).json()
    assert joined["ok"] is True
    assert joined["link_id"] == link_id
    assert joined["offer"] == OFFER

    put = client.post(f"/api/near/links/{link_id}/answer", json={"answer": ANSWER}, cookies=_cookie(A))
    assert put.json() == {"ok": True}

    peek = client.get(f"/api/near/links/{link_id}", cookies=host).json()
    assert peek["claimed"] is True
    assert peek["answer"] == ANSWER

    assert client.delete(f"/api/near/links/{link_id}", cookies=host).json()["ok"] is True
    gone = client.get(f"/api/near/links/{link_id}", cookies=host)
    assert gone.status_code == 404


def test_other_account_cannot_take_the_link(client):
    client.post("/api/near/links", json={"offer": OFFER}, cookies=_cookie(A))
    other = client.post("/api/near/links/claim", cookies=_cookie(B))
    assert other.status_code == 404
    assert other.json()["error"] == "no_open_link"


def test_link_is_taken_once_and_newest_first(client):
    host = _cookie(A)
    first = client.post("/api/near/links", json={"offer": OFFER}, cookies=host).json()["link_id"]
    near_links._mem[f"{A}/{first}"]["created_at"] -= 5
    second = client.post("/api/near/links", json={"offer": OFFER}, cookies=host).json()["link_id"]
    got = client.post("/api/near/links/claim", cookies=host).json()
    assert got["link_id"] == second
    got2 = client.post("/api/near/links/claim", cookies=host).json()
    assert got2["link_id"] == first
    assert client.post("/api/near/links/claim", cookies=host).status_code == 404


def test_answer_needs_claim_and_only_once(client):
    host = _cookie(A)
    link_id = client.post("/api/near/links", json={"offer": OFFER}, cookies=host).json()["link_id"]
    early = client.post(f"/api/near/links/{link_id}/answer", json={"answer": ANSWER}, cookies=host)
    assert early.status_code == 409
    assert early.json()["error"] == "not_claimed"
    client.post("/api/near/links/claim", cookies=host)
    assert client.post(f"/api/near/links/{link_id}/answer", json={"answer": ANSWER}, cookies=host).status_code == 200
    again = client.post(f"/api/near/links/{link_id}/answer", json={"answer": ANSWER}, cookies=host)
    assert again.json()["error"] == "answered"


def test_expired_link_is_gone(client):
    host = _cookie(A)
    link_id = client.post("/api/near/links", json={"offer": OFFER}, cookies=host).json()["link_id"]
    near_links._mem[f"{A}/{link_id}"]["expires_at"] = 0
    assert client.get(f"/api/near/links/{link_id}", cookies=host).status_code == 410
    assert f"{A}/{link_id}" not in near_links._mem
    assert client.post("/api/near/links/claim", cookies=host).status_code == 404


def test_bad_inputs(client):
    host = _cookie(A)
    assert client.post("/api/near/links", json={"offer": ANSWER}, cookies=host).status_code == 400
    assert client.post("/api/near/links", json={}, cookies=host).status_code == 400
    huge = {"type": "offer", "sdp": "x" * (near_links.MAX_SDP_BYTES + 1)}
    assert client.post("/api/near/links", json={"offer": huge}, cookies=host).status_code == 400
    assert client.get("/api/near/links/short", cookies=host).status_code == 400
    assert client.get("/api/near/links/" + "a" * 20 + ".x", cookies=host).status_code == 400


def test_needs_login(client):
    res = client.post("/api/near/links", json={"offer": OFFER})
    assert res.status_code == 401


LIB = __import__("pathlib").Path(__file__).resolve().parents[1] / "mobile" / "lib"


def _dart(rel: str) -> str:
    return (LIB / rel).read_text(encoding="utf-8").replace("\r\n", "\n")


def test_frames_are_all_binary():
    text = _dart("services/near_link.dart")
    assert "RTCDataChannelMessage.fromBinary(frame)" in text
    assert "RTCDataChannelMessage(" not in text


def test_description_is_sent_after_gathering():
    text = _dart("services/near_link.dart")
    host = text[text.index("Future<void> host()"):text.index("Future<void> join()")]
    assert host.index("_gathered(pc)") < host.index("client.nearCreateLink(")
    join = text[text.index("Future<void> join()"):text.index("Future<void> cancel()")]
    assert join.index("_gathered(pc)") < join.index("client.nearPutAnswer(")


def test_sync_never_deletes():
    text = _dart("services/near_sync.dart") + _dart("services/near_library_local.dart")
    assert "purge(" not in text
    assert "removeFromIndex(" not in text


def test_library_has_the_button_and_both_kind_lists_know_the_event():
    assert "showNearSyncSheet(" in _dart("screens/library_screen.dart")
    assert "'near_sync_done'" in _dart("services/evidence_kinds.dart")
    from sentence_reading.llm.evidence_kinds import ALLOWED_KINDS

    assert "near_sync_done" in ALLOWED_KINDS


def test_relay_bundles_pass_once_and_are_deleted(client):
    a = _cookie(A)
    link = "r" * 20
    assert client.get(f"/api/near/relay/{link}/h/0", cookies=a).status_code == 204
    assert client.post(f"/api/near/relay/{link}/h/0", content=b"one", cookies=a).json()["ok"] is True
    assert client.post(f"/api/near/relay/{link}/h/1", content=b"two", cookies=a).json()["ok"] is True
    got = client.get(f"/api/near/relay/{link}/h/0", cookies=a)
    assert got.status_code == 200
    assert got.content == b"one"
    assert client.get(f"/api/near/relay/{link}/h/1", cookies=a).content == b"two"
    assert f"{A}/relay/{link}/h/00000000" not in near_links._mem
    assert client.get(f"/api/near/relay/{link}/j/0", cookies=a).status_code == 204
    assert client.get(f"/api/near/relay/{link}/h/0", cookies=_cookie(B)).status_code == 204
    assert client.delete(f"/api/near/relay/{link}", cookies=a).json()["ok"] is True
    assert not [k for k in near_links._mem if "/relay/" in k]


def test_relay_rejects_bad_input(client):
    a = _cookie(A)
    link = "r" * 20
    assert client.post(f"/api/near/relay/{link}/x/0", content=b"1", cookies=a).status_code == 400
    assert client.post(f"/api/near/relay/short/h/0", content=b"1", cookies=a).status_code == 400
    assert client.post(f"/api/near/relay/{link}/h/0", content=b"", cookies=a).status_code == 413
    big = b"x" * (near_links.RELAY_MAX_BYTES + 1)
    assert client.post(f"/api/near/relay/{link}/h/0", content=big, cookies=a).status_code == 413


def test_new_link_wipes_relay_leftovers(client):
    a = _cookie(A)
    link = "r" * 20
    client.post(f"/api/near/relay/{link}/h/5", content=b"left", cookies=a)
    client.post("/api/near/links", json={"offer": OFFER}, cookies=a)
    assert not [k for k in near_links._mem if "/relay/" in k]


def test_relay_frames_are_dropped_after_sync():
    text = _dart("services/near_link.dart")
    assert "nearRelayWipe(" in text
    assert "kNearDirectLimit" in text


def test_shadowing_store_goes_through_disk_fs():
    text = _dart("services/shadowing_disk_store.dart")
    body = text[text.index("Future<DiskFile?> _chunkPlanFile("):]
    assert not __import__("re").search(r"(?<![A-Za-z_])(File|Directory)\(", body)
    assert "if (!browserDiskAvailable) return null;" in text


def test_sync_report_says_where_the_time_went():
    link = _dart("services/near_link.dart")
    for key in ("'open_ms'", "'local_kind'", "'remote_kind'", "'rtt_ms'", "...?r?.times"):
        assert key in link, key
    sync = _dart("services/near_sync.dart")
    for key in ("'pack_ms'", "'send_ms'", "'room_ms'", "'store_ms'", "'sync_ms'"):
        assert key in sync, key
