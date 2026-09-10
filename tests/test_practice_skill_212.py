"""design/212 — practice skill score + spoken SoT + kill."""

from sentence_reading.llm.practice_skill import (
    practice_skill_enabled,
    practice_stt_cloud_enabled,
)
from sentence_reading.llm.practice_skill_score import content_word_coverage
from sentence_reading.llm.tts_speak import spoken_text_for_tts
from sentence_reading.llm.tts_speak_policy import speak_norm_version


def test_skill_kill_env(monkeypatch):
    monkeypatch.delenv("ASR_PRACTICE_SKILL", raising=False)
    assert practice_skill_enabled() is True
    monkeypatch.setenv("ASR_PRACTICE_SKILL", "0")
    assert practice_skill_enabled() is False
    assert practice_stt_cloud_enabled() is False


def test_content_word_coverage_order_insensitive():
    spoken = "catalyst prepared carefully"
    heard = "carefully prepared catalyst extra noise"
    r = content_word_coverage(spoken, heard)
    assert r["ok"] is True
    assert r["accuracy"] is not None
    assert r["accuracy"] >= 0.99


def test_content_word_coverage_empty_ref():
    r = content_word_coverage("the a of", "hello")
    assert r["ok"] is False
    assert r["error"] == "empty_content_ref"


def test_spoken_sot_and_version():
    display = "Ni catalyst"
    spoken = spoken_text_for_tts(display)
    assert spoken
    assert speak_norm_version()
    # Idempotent
    assert spoken_text_for_tts(spoken) == spoken
