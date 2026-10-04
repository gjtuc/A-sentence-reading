"""design/389 - a practice chunk borrows its sentence's reference sounds.

The paper warm builds whole sentences, and practice plays growing fronts of them.
Every front used to cost its own build while the reader waited.
"""

from __future__ import annotations

import json
import re

from sentence_reading.llm import sound_reference as sr
from sentence_reading.llm.sound_reference import whole_line
from sentence_reading.llm.tts_speak import spoken_text_for_tts

SENTENCE = "The film grew at five hundred degrees in pure argon."
CHUNK = "The film grew at five hundred degrees"


def _seed(tmp_path, monkeypatch, display: str) -> str:
    monkeypatch.setenv("ASR_SOUND_REF_DIR", str(tmp_path))
    monkeypatch.setenv("ASR_SOUND_REF", "1")
    monkeypatch.setenv("ASR_ACCESS_GATE", "0")
    spoken = spoken_text_for_tts(display)
    words = [
        {"lo": m.start(), "hi": m.end(), "sounds": " ".join(m.group(0).lower()),
         "share": ""}
        for m in re.finditer(r"\S+", spoken)
    ]
    got = {"voice": sr.reference_voice(), "words": words,
           "natural_n": 0, "mark_n": len(words)}
    key = sr.cache_key(spoken, sr.reference_voice())
    (tmp_path / f"{key}.json").write_text(json.dumps(got), encoding="utf-8")
    return spoken


def test_design_389_only_a_front_at_a_word_edge_is_lent():
    assert whole_line("the film grew", "the film grew hot") == ("the film grew hot", "front")
    assert whole_line("the film grew,", "the film grew, hot")[1] == "front"
    # Cut inside a word: `grew` is not `grewn`.
    assert whole_line("the film grew", "the film grewn")[1] == "not_front"
    assert whole_line("the film grew", "a film grew hot")[1] == "not_front"
    assert whole_line("the film grew", "the film grew") == ("", "same")
    assert whole_line("the film grew", "") == ("", "none")


def test_design_389_the_chunk_takes_the_sentence_sounds(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from sentence_reading.api.app import app

    _seed(tmp_path, monkeypatch, SENTENCE)
    asked: list[str] = []
    monkeypatch.setattr(sr, "build", lambda spoken, **kw: asked.append(spoken))
    got = TestClient(app).post(
        "/api/tts/spoken", json={"text": CHUNK, "whole_text": SENTENCE}
    ).json()
    assert got["ok"] is True
    assert got["sound_ref_code"] == "sliced"
    by = {CHUNK[s["start"]:s["end"]]: s["phone"] for s in got["spans"]}
    assert by["grew"] == "g r e w"
    assert by["degrees"] == "d e g r e e s"
    # The sentence's later words belong to nobody in this chunk.
    assert all("a r g o n" not in s["phone"] for s in got["spans"])
    assert asked == []


def test_design_389_a_chunk_of_its_own_still_wins(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from sentence_reading.api.app import app

    _seed(tmp_path, monkeypatch, SENTENCE)
    _seed(tmp_path, monkeypatch, CHUNK)
    got = TestClient(app).post(
        "/api/tts/spoken", json={"text": CHUNK, "whole_text": SENTENCE}
    ).json()
    assert got["sound_ref_code"] == "ready"


def test_design_389_a_miss_builds_the_sentence_not_the_chunk(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from sentence_reading.api.app import app

    monkeypatch.setenv("ASR_SOUND_REF_DIR", str(tmp_path))
    monkeypatch.setenv("ASR_SOUND_REF", "1")
    monkeypatch.setenv("ASR_ACCESS_GATE", "0")
    seen: list[str] = []
    monkeypatch.setattr(sr, "request_build", lambda spoken, **kw: seen.append(spoken) or "queued")
    got = TestClient(app).post(
        "/api/tts/spoken", json={"text": CHUNK, "whole_text": SENTENCE}
    ).json()
    assert got["sound_ref_code"] == "queued"
    assert seen == [spoken_text_for_tts(SENTENCE)]


def test_design_389_a_sentence_that_is_not_the_front_is_ignored(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from sentence_reading.api.app import app

    _seed(tmp_path, monkeypatch, "A thin layer forms on the surface of the gold.")
    seen: list[str] = []
    monkeypatch.setattr(sr, "request_build", lambda spoken, **kw: seen.append(spoken) or "queued")
    got = TestClient(app).post(
        "/api/tts/spoken",
        json={"text": CHUNK, "whole_text": "A thin layer forms on the surface of the gold."},
    ).json()
    assert got["sound_ref_code"] == "queued"
    assert seen == [spoken_text_for_tts(CHUNK)]
