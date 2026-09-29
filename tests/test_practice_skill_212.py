"""design/212 — practice skill score + spoken SoT + kill.

design/370 — the slot tests below hand over reference sounds, not a transcript.
Every test that asserted a decision made from letters a recognizer typed was
removed: spelling variants, element symbols, digit-letter splits, possessive
marks, number words, and the content-word scorer. See design/368 and design/370.
"""

import pathlib

from sentence_reading.llm.practice_skill import (
    practice_skill_enabled,
    practice_stt_cloud_enabled,
)
from sentence_reading.llm.practice_skill_score import (
    SOUND_REF_MISSING,
    spoken_slot_coverage,
)
from sentence_reading.llm.tts_speak import spoken_text_for_tts
from sentence_reading.llm.tts_speak_policy import speak_norm_version

# Reference sounds for "The film grew". Ascii on purpose: the compare counts
# units, so this reads the same as IPA and stays legible in a diff.
_THE = "d i"
_FILM = "f i l m"
_GREW = "g r uu"


def _spans() -> list[dict]:
    return [
        {"start": 0, "end": 3, "weight": 4, "phone": _THE},
        {"start": 4, "end": 8, "weight": 5, "phone": _FILM},
        {"start": 9, "end": 13, "weight": 4, "phone": _GREW},
    ]


def test_skill_kill_env(monkeypatch):
    monkeypatch.delenv("ASR_PRACTICE_SKILL", raising=False)
    assert practice_skill_enabled() is True
    monkeypatch.setenv("ASR_PRACTICE_SKILL", "0")
    assert practice_skill_enabled() is False
    assert practice_stt_cloud_enabled() is False

def test_spoken_sot_and_version():
    display = "Ni catalyst"
    spoken = spoken_text_for_tts(display)
    assert spoken
    assert speak_norm_version()
    # Idempotent
    assert spoken_text_for_tts(spoken) == spoken

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

def test_design_366_a_word_is_found_inside_the_whole_run() -> None:
    from sentence_reading.llm.phone_match import phones_close

    # The waveform model returns one run of sounds for the whole take.
    run = "ð ə k æ t ə l ɪ s t d ɪ s p ɜ ʃ ə n w ɒ z h aɪ"
    assert phones_close("dɪspˈɜːʃən", run) is True
    # A word that was never read stays out, with the whole run to search.
    assert phones_close("vənˈeɪdiəm", run) is False

def test_design_366_a_short_target_is_not_judged_by_sound() -> None:
    from sentence_reading.llm.phone_match import phones_close

    # Two sounds match too much of anything to carry a slot.
    assert phones_close("ðə", "ð ə k æ t") is False

def test_design_366_the_window_allows_one_split_sound() -> None:
    from sentence_reading.llm.phone_match import best_window_overlap

    left = ["k", "æ", "t"]
    # An extra sound inside the stretch still reads as the same word.
    assert best_window_overlap(left, ["b", "k", "æ", "ə", "t", "s"]) >= 0.72
    # A different word does not.
    assert best_window_overlap(left, ["d", "ɒ", "g"]) < 0.72


def test_design_370_a_take_with_no_reference_sounds_is_not_scored() -> None:
    bare = [{k: v for k, v in s.items() if k != "phone"} for s in _spans()]
    out = spoken_slot_coverage("The film grew", "The film grew", bare, _FILM)
    # Calling this 0% would blame the reader for a missing reference.
    assert out["ok"] is False
    assert out["error"] == SOUND_REF_MISSING
    assert out["accuracy"] is None


def test_design_370_a_word_is_judged_by_its_sounds() -> None:
    heard = f"{_FILM} {_GREW}"
    out = spoken_slot_coverage("The film grew", "The film grew", _spans(), heard)
    assert out["ok"] is True
    assert out["ref_n"] == 3
    # `The` is two sounds, under the floor in design/366, so sound cannot judge it.
    assert out["hit_n"] == 2
    assert out["missed"] == [{"start": 0, "end": 3}]


def test_design_370_a_silent_take_misses_every_slot() -> None:
    out = spoken_slot_coverage("The film grew", "The film grew", _spans(), "")
    assert out["ok"] is True
    assert out["hit_n"] == 0
    assert len(out["missed"]) == 3


def test_design_370_a_word_is_found_wherever_it_sits_in_the_run() -> None:
    # The run holds the whole take, so a later word must still be found.
    heard = f"{_THE} {_FILM} {_GREW}"
    out = spoken_slot_coverage("The film grew", "The film grew", _spans(), heard)
    assert out["hit_n"] == 2
    assert {"start": 9, "end": 13} not in out["missed"]


def test_design_370_the_twins_agree_on_the_threshold() -> None:
    """Dart and Python must fail the same word, or the two halves drift."""
    from sentence_reading.llm import phone_match

    dart = (
        pathlib.Path(__file__).resolve().parents[1]
        / "mobile"
        / "lib"
        / "practice_skill"
        / "skill_score.dart"
    ).read_text(encoding="utf-8")
    assert f"kPhoneOverlapMin = {phone_match._OVERLAP_MIN}" in dart
    assert f"kPhoneMinUnits = {phone_match._MIN_PHONES}" in dart
    assert f"kSoundRefMissing = '{SOUND_REF_MISSING}'" in dart


def test_marks_between_words_do_not_shift_the_next_slot() -> None:
    from sentence_reading.llm.tts_speak import align_display_to_spoken

    display = "Consequently, the single cell; performance. Done."
    spoken = spoken_text_for_tts(display)
    spans = align_display_to_spoken(display)
    # A comma must not become the first letters of the next slot. Give every
    # span the same sound and the whole run, so only the walk can fail.
    for span in spans:
        if int(span.get("weight") or 0) > 0:
            span["phone"] = _FILM
    out = spoken_slot_coverage(display, spoken, spans, _FILM)
    assert out["ok"] is True
    assert out["ref_n"] == 6
    assert out["hit_n"] == 6
