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


def test_one_word_symbols_are_cut_into_single_sounds() -> None:
    from sentence_reading.llm.phone_match import phones_close, split_phone_units

    # eSpeak hands back a whole word as one run. The waveform model hands back
    # one sound at a time, so a run has to be cut before the two can be compared.
    assert split_phone_units("dɪspˈɜːʃən") == ["d", "ɪ", "s", "p", "ɜ", "ʃ", "ə", "n"]
    assert split_phone_units("d ɪ s p ɜ ʃ ə n") == split_phone_units("dɪspˈɜːʃən")
    assert split_phone_units("") == []
    assert phones_close("dɪspˈɜːʃən", "d ɪ s p ɜ ʃ ə n") is True
    assert phones_close("dɪspˈɜːʃən", "k ɑː b ə n") is False


def test_a_spoken_abbreviation_does_not_shift_the_line() -> None:
    from sentence_reading.llm.tts_speak import align_display_report

    # `voice_definitions` reads `(CV)` aloud, so the aside drop must not hide it
    # from the aligner. It used to, and every later word took the wrong sound.
    display = "The area measured by cyclic voltammetry (CV) is small."
    report = align_display_report(display)
    assert report["code"] == "ok"
    assert report["renamed_n"] == 0
    # A plain aside is still skipped.
    aside = align_display_report("The area is small (data not shown).")
    assert aside["code"] == "ok"


def test_design_365_a_spelling_variant_is_not_a_missed_word() -> None:
    from sentence_reading.llm.practice_skill_score import spoken_slot_coverage

    display = "Vanadium vapour was absorbed"
    spoken = "Vanadium vapour was absorbed"
    spans = [
        {"start": 0, "end": 8, "weight": 8},
        {"start": 9, "end": 15, "weight": 6},
        {"start": 16, "end": 19, "weight": 3},
        {"start": 20, "end": 28, "weight": 8},
    ]
    # The recognizer answers in American spelling; the speaker read it right.
    out = spoken_slot_coverage(
        display, spoken, spans, "Vanadium vapor was absorbed"
    )
    assert out["ok"] is True
    assert out["hit_n"] == 4
    assert out["missed"] == []


def test_design_365_an_element_symbol_may_come_back_as_its_name() -> None:
    from sentence_reading.llm.practice_skill_score import spoken_slot_coverage

    display = "The Ni 2p peak"
    spoken = "The Ni two p peak"
    spans = [
        {"start": 0, "end": 3, "weight": 3},
        {"start": 4, "end": 6, "weight": 2},
        {"start": 7, "end": 8, "weight": 3},
        {"start": 8, "end": 9, "weight": 1},
        {"start": 10, "end": 14, "weight": 4},
    ]
    # The voice says "nickel" and writes `2p` as one token; nothing was misread.
    out = spoken_slot_coverage(display, spoken, spans, "The nickel 2p peak")
    assert out["ok"] is True
    assert out["hit_n"] == 5
    assert out["missed"] == []


def test_design_365_an_apostrophe_is_not_a_slot() -> None:
    from sentence_reading.llm.practice_skill_score import spoken_slot_coverage

    display = "Both catalysts' strengths"
    spoken = "Both catalysts' strengths"
    # The aligner really does hand the apostrophe its own one-character span.
    spans = [
        {"start": 0, "end": 4, "weight": 4},
        {"start": 5, "end": 14, "weight": 9},
        {"start": 14, "end": 15, "weight": 1},
        {"start": 16, "end": 25, "weight": 9},
    ]
    out = spoken_slot_coverage(
        display, spoken, spans, "Both catalysts strengths"
    )
    assert out["ok"] is True
    # Three scorable slots, not four: the lone apostrophe capped this line at 3/4
    # however it was read.
    assert out["ref_n"] == 3
    assert out["hit_n"] == 3


def test_design_365_a_real_miss_still_misses() -> None:
    from sentence_reading.llm.practice_skill_score import spoken_slot_coverage

    display = "Vanadium vapour was absorbed"
    spoken = "Vanadium vapour was absorbed"
    spans = [
        {"start": 0, "end": 8, "weight": 8},
        {"start": 9, "end": 15, "weight": 6},
        {"start": 16, "end": 19, "weight": 3},
        {"start": 20, "end": 28, "weight": 8},
    ]
    # `paper` for `vapour` and `observed` for `absorbed` are real confusions.
    out = spoken_slot_coverage(
        display, spoken, spans, "Vanadium paper was observed"
    )
    assert out["hit_n"] == 2
    assert len(out["missed"]) == 2


def test_design_365_a_possessive_mark_is_not_a_sound() -> None:
    from sentence_reading.llm.practice_skill_score import spoken_slot_coverage

    display = "Both catalysts' strengths"
    spoken = "Both catalysts' strengths"
    # Here the apostrophe rides along inside the word span instead of getting one
    # of its own, so the slot token is `catalysts'`.
    spans = [
        {"start": 0, "end": 4, "weight": 4},
        {"start": 5, "end": 15, "weight": 10},
        {"start": 16, "end": 25, "weight": 9},
    ]
    out = spoken_slot_coverage(
        display, spoken, spans, "Both catalysts strengths"
    )
    assert out["ref_n"] == 3
    assert out["hit_n"] == 3
