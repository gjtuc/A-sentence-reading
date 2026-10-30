# -*- coding: utf-8 -*-
"""design/490 - a reader's title and kind for a paper: per account, newer wins."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from sentence_reading.api.app import app
from sentence_reading.llm import auth_google as ag
from sentence_reading.llm import paper_labels, voice_question
from sentence_reading.llm.auth_google import AuthUser

A = "118234567890123456011"
B = "118234567890123456012"
PHONE = "phoneDEV0000000001"
WEB = "webDEV000000000002"


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setenv("ASR_AUTH_SECRET", "test-secret-paper-labels-xxxxxxxxx")
    monkeypatch.setenv("ASR_ACCESS_GATE", "0")
    monkeypatch.setattr(paper_labels, "_use_gcs", lambda: False)
    paper_labels.reset_memory_for_tests()
    yield TestClient(app)
    paper_labels.reset_memory_for_tests()


def _cookie(uid: str) -> dict[str, str]:
    user = AuthUser(uid=uid, email=f"{uid[-4:]}@example.com", name="N", picture="")
    return {ag.COOKIE_NAME: ag.issue_session_token(user)}


def _label(at: str, dev: str = PHONE, **fields) -> dict:
    return {"at": at, "dev": dev, **fields}


def test_a_title_and_kind_are_kept(client):
    c = _cookie(A)
    body = _label("2026-10-30T10:00:00Z", t="니켈 구리 합금 논문", k="review")
    r = client.put("/api/paper-labels/abc123", json=body, cookies=c)
    assert r.json() == {"ok": True, "rev": 1, "applied": True}
    page = client.get("/api/paper-labels", cookies=c).json()
    assert page["labels"] == {"abc123": body}


def test_a_newer_label_replaces_the_whole_label(client):
    c = _cookie(A)
    client.put("/api/paper-labels/abc123", json=_label("2026-10-30T10:00:00Z", t="X", k="general"), cookies=c)
    r = client.put("/api/paper-labels/abc123", json=_label("2026-10-30T10:05:00Z", WEB), cookies=c)
    assert r.json()["applied"] is True
    r = client.put("/api/paper-labels/abc123", json=_label("2026-10-30T10:01:00Z", t="old"), cookies=c)
    assert r.json()["applied"] is False
    assert client.get("/api/paper-labels", cookies=c).json()["labels"]["abc123"] == _label(
        "2026-10-30T10:05:00Z", WEB
    )


def test_accounts_do_not_see_each_other(client):
    client.put("/api/paper-labels/abc123", json=_label("2026-10-30T10:00:00Z", t="X"), cookies=_cookie(A))
    assert client.get("/api/paper-labels", cookies=_cookie(B)).json()["labels"] == {}


def test_bad_input_is_refused(client):
    c = _cookie(A)
    at = "2026-10-30T10:00:00Z"
    assert client.put("/api/paper-labels/abc123", json=_label(at, k="poem"), cookies=c).status_code == 400
    assert client.put("/api/paper-labels/abc123", json=_label(at, t="   "), cookies=c).status_code == 400
    assert client.put("/api/paper-labels/abc123", json=_label(at, t="x" * 301), cookies=c).status_code == 400
    assert client.put("/api/paper-labels/abc123", json={"t": "X"}, cookies=c).status_code == 400
    assert client.put("/api/paper-labels/abc123", json=_label(at, t="X")).status_code == 401


def test_title_spaces_are_folded():
    out = paper_labels.clean_label(_label("2026-10-30T10:00:00Z", t="  A \n  B  "))
    assert out and out["t"] == "A B"


def test_title_voice_uses_the_title_prompt(monkeypatch):
    seen = {}

    def fake(audio, mime, sentence, purpose="question"):
        seen.update(sentence=sentence, purpose=purpose)
        return "니켈 촉매 정리."

    monkeypatch.setattr(voice_question, "_call", fake)
    monkeypatch.setattr(voice_question, "gemini_api_key", lambda: "k")
    out = voice_question.transcribe_question(
        b"abc", mime="audio/mp4", sentence="Old title", purpose="title"
    )
    assert out.text == "니켈 촉매 정리"
    assert seen == {"sentence": "Old title", "purpose": "title"}


def test_title_voice_route_passes_the_purpose(monkeypatch):
    seen = {}

    def fake(data, *, mime, sentence, purpose="question"):
        seen["purpose"] = purpose
        return voice_question.VoiceQuestion("T", "ok", 5)

    monkeypatch.setattr(voice_question, "transcribe_question", fake)
    res = TestClient(app).post(
        "/api/ask/voice",
        files={"file": ("q.webm", b"abcd", "audio/webm")},
        data={"sentence": "Old", "purpose": "title"},
    )
    assert res.json()["text"] == "T" and seen["purpose"] == "title"
