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


def test_cvd_counts_as_one_spoken_slot():
    from sentence_reading.llm.practice_skill_score import spoken_slot_coverage
    from sentence_reading.llm.tts_speak import align_display_to_spoken

    display = "CVD is a technique for semiconductor."
    spoken = spoken_text_for_tts(display)
    spans = align_display_to_spoken(display)
    assert spans
    tokens = spoken.split()
    assert tokens[0].lower() == "c"
    heard = " ".join(tokens[1:])
    scored = spoken_slot_coverage(display, spoken, spans, heard)
    assert scored["ok"] is True
    assert scored["ref_n"] == 6
    assert scored["hit_n"] == 5
    assert scored["missed"] == [{"start": 0, "end": 3}]


def test_marks_between_words_do_not_shift_the_next_slot():
    from sentence_reading.llm.practice_skill_score import spoken_slot_coverage
    from sentence_reading.llm.tts_speak import align_display_to_spoken

    display = "Consequently, the single cell; performance. Done."
    spoken = spoken_text_for_tts(display)
    spans = align_display_to_spoken(display)
    scored = spoken_slot_coverage(display, spoken, spans, spoken)
    assert scored["ok"] is True
    assert scored["ref_n"] == 6
    assert scored["hit_n"] == 6
    assert scored["missed"] == []


def test_letter_spelled_slot_matches_joined_word():
    from sentence_reading.llm.practice_skill_score import spoken_slot_coverage

    display = "CVD is ready"
    spoken = "c v d is ready"
    spans = [
        {"start": 0, "end": 3, "weight": 5},
        {"start": 4, "end": 6, "weight": 2},
        {"start": 7, "end": 12, "weight": 5},
    ]
    joined = spoken_slot_coverage(display, spoken, spans, "cvd is ready")
    assert joined["hit_n"] == 3
    assert joined["missed"] == []
    short = spoken_slot_coverage(display, spoken, spans, "cv is ready")
    assert short["hit_n"] == 2
    assert short["missed"] == [{"start": 0, "end": 3}]


def test_they_are_counts_as_their():
    from sentence_reading.llm.phone_match import phones_close
    from sentence_reading.llm.practice_skill_score import spoken_slot_coverage

    display = "Their"
    spoken = "Their"
    spans = [{"start": 0, "end": 5, "weight": 5}]
    scored = spoken_slot_coverage(display, spoken, spans, "they are")
    assert scored["hit_n"] == 1
    assert phones_close("k æ t ə l ɪ s t", "d ɒ g") is False
    assert phones_close("ə", "eɪ") is False


def test_spoken_sot_and_version():
    display = "Ni catalyst"
    spoken = spoken_text_for_tts(display)
    assert spoken
    assert speak_norm_version()
    # Idempotent
    assert spoken_text_for_tts(spoken) == spoken

def test_a_digit_slot_accepts_the_spoken_number() -> None:
    from sentence_reading.llm.practice_skill_score import spoken_slot_coverage

    display = "approximately 1 nm"
    spoken = "approximately 1 nanometers"
    spans = [
        {"start": 0, "end": 13, "weight": 13},
        {"start": 14, "end": 15, "weight": 1},
        {"start": 16, "end": 18, "weight": 10},
    ]
    out = spoken_slot_coverage(display, spoken, spans, "approximately one nanometer")
    assert out["ok"] is True
    assert out["hit_n"] == 3
    assert out["missed"] == []


def test_a_wrong_word_is_still_missed_with_the_number_rule() -> None:
    from sentence_reading.llm.practice_skill_score import spoken_slot_coverage

    display = "approximately 1 nm"
    spoken = "approximately 1 nanometers"
    spans = [
        {"start": 0, "end": 13, "weight": 13},
        {"start": 14, "end": 15, "weight": 1},
        {"start": 16, "end": 18, "weight": 10},
    ]
    out = spoken_slot_coverage(display, spoken, spans, "approximately two meters")
    assert out["hit_n"] == 1
    assert len(out["missed"]) == 2
