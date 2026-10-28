"""design/475 — spoken AI question: the route writes it down with the sentence."""

from __future__ import annotations

from fastapi.testclient import TestClient

from sentence_reading.api import app as app_mod
from sentence_reading.llm import evidence_kinds, voice_question


def test_voice_question_kinds_are_allowed():
    assert "voice_ask_transcribe" in evidence_kinds.ALLOWED_KINDS
    assert "voice_ask_client" in evidence_kinds.ALLOWED_KINDS


def test_mime_is_reduced_to_what_gemini_takes():
    assert voice_question.audio_mime("audio/webm;codecs=opus") == "audio/webm"
    assert voice_question.audio_mime("audio/mp4") == "audio/mp4"
    assert voice_question.audio_mime("") == "audio/mp4"


def test_clean_keeps_one_line_and_drops_wrapping_quotes():
    assert voice_question._clean('  "이 문장에서\n  catalyst 가 뭐야?"  ') == "이 문장에서 catalyst 가 뭐야?"
    assert voice_question._clean("") == ""


def test_empty_and_oversized_audio_never_call_gemini(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("no call")

    monkeypatch.setattr(voice_question, "_call", boom)
    monkeypatch.setattr(voice_question, "gemini_api_key", lambda: "k")
    assert voice_question.transcribe_question(b"", mime="audio/mp4", sentence="s").code == "empty_audio"
    big = b"x" * (voice_question.MAX_AUDIO_BYTES + 1)
    assert voice_question.transcribe_question(big, mime="audio/mp4", sentence="s").code == "audio_too_large"


def test_the_sentence_goes_with_the_audio(monkeypatch):
    seen = {}

    def fake(audio, mime, sentence):
        seen.update(audio=audio, mime=mime, sentence=sentence)
        return " 음 이 catalyst 가 뭐야 \n"

    monkeypatch.setattr(voice_question, "_call", fake)
    monkeypatch.setattr(voice_question, "gemini_api_key", lambda: "k")
    out = voice_question.transcribe_question(
        b"abc", mime="audio/webm;codecs=opus", sentence="The catalyst works."
    )
    assert out.code == "ok"
    assert out.text == "음 이 catalyst 가 뭐야"
    assert seen == {"audio": b"abc", "mime": "audio/webm", "sentence": "The catalyst works."}


def test_route_returns_the_text(monkeypatch):
    monkeypatch.setattr(
        voice_question,
        "transcribe_question",
        lambda data, *, mime, sentence: voice_question.VoiceQuestion(
            f"{len(data)}:{sentence}", "ok", 5
        ),
    )
    client = TestClient(app_mod.app)
    res = client.post(
        "/api/ask/voice",
        files={"file": ("q.webm", b"abcd", "audio/webm")},
        data={"sentence": "The cat sat."},
    )
    assert res.status_code == 200
    assert res.json() == {"ok": True, "text": "4:The cat sat.", "ms": 5}


def test_route_failure_is_not_ok(monkeypatch):
    monkeypatch.setattr(
        voice_question,
        "transcribe_question",
        lambda data, *, mime, sentence: voice_question.VoiceQuestion("", "timeout", 60000),
    )
    client = TestClient(app_mod.app)
    res = client.post("/api/ask/voice", files={"file": ("q.m4a", b"a", "audio/mp4")})
    assert res.status_code == 502
    assert res.json() == {"ok": False, "error": "timeout"}
