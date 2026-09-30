"""design/371 — the reference sounds, and how they reach a printed word.

Nothing here talks to Google or loads the model. The parts that do are the two
synthesis calls and the two model passes in `build`, which are covered by
`scripts/neighbor_swap_probe.py` against real audio. What is tested here is the
bookkeeping that decides which word gets which sounds, because that is where a
mistake is silent: the scorer cannot tell a wrong reference from a right one.
"""

from __future__ import annotations

from sentence_reading.llm.sound_reference import (
    BREAK_MS,
    attach_sounds,
    cache_key,
    hand_out,
    ssml_marked,
    strip_ranges,
)
from sentence_reading.llm.tts_speak import align_display_report, spoken_text_for_tts


def test_design_371_every_token_gets_a_mark_pair_numbers_included():
    ssml, spots = ssml_marked("The size grew from 2.3 nm.")
    assert [t for _lo, _hi, t in spots] == [
        "The", "size", "grew", "from", "2.3", "nm.",
    ]
    # A number with no letters in it still needs its own window, or `hand_out`
    # has to force its sounds onto a neighbour.
    for i in range(len(spots)):
        assert f'<mark name="w{i}"/>' in ssml
        assert f'<mark name="e{i}"/>' in ssml
    assert f'<break time="{BREAK_MS}ms"/>' in ssml


def test_design_371_the_spots_point_back_at_the_text():
    line = "The size grew from 2.3 nm."
    _ssml, spots = ssml_marked(line)
    for lo, hi, token in spots:
        assert line[lo:hi] == token


def test_design_371_a_reference_token_is_handed_out_only_once():
    # Printed `2.3` is two spans because the display splits on the dot, while
    # the voice reads one token. Both spans overlap it.
    spans = [
        {"start": 0, "end": 1, "weight": 1, "spoken_lo": 0, "spoken_hi": 1},
        {"start": 2, "end": 3, "weight": 1, "spoken_lo": 2, "spoken_hi": 3},
    ]
    got = {"words": [{"lo": 0, "hi": 3, "sounds": "t u p"}]}
    filled = attach_sounds(spans, got)
    assert filled == 1
    assert spans[0]["phone"] == "t u p"
    # Empty, not a copy. A copy would score the same audio twice and let one
    # slip pass on the other's sounds.
    assert spans[1]["phone"] == ""


def test_design_371_a_span_reading_two_tokens_gets_both():
    spans = [{"start": 0, "end": 5, "weight": 9, "spoken_lo": 0, "spoken_hi": 9}]
    got = {
        "words": [
            {"lo": 0, "hi": 4, "sounds": "a b"},
            {"lo": 5, "hi": 9, "sounds": "c d"},
        ]
    }
    assert attach_sounds(spans, got) == 1
    assert spans[0]["phone"] == "a b c d"


def test_design_371_a_span_with_no_spoken_slice_gets_nothing():
    # A dropped parenthetical is printed but never read.
    spans = [{"start": 0, "end": 5, "weight": 0, "spoken_lo": 3, "spoken_hi": 3}]
    got = {"words": [{"lo": 0, "hi": 9, "sounds": "a b"}]}
    assert attach_sounds(spans, got) == 0
    assert spans[0]["phone"] == ""


def test_design_371_a_missing_reference_still_puts_the_key_on_every_span():
    spans = [{"start": 0, "end": 3, "weight": 3, "spoken_lo": 0, "spoken_hi": 3}]
    assert attach_sounds(spans, None) == 0
    # The client defaults a missing `phone` to empty, so a half-written span
    # would look the same as a scored one. Always write the key.
    assert spans[0]["phone"] == ""


def test_design_371_strip_ranges_leaves_only_the_wire_keys():
    spans = [{"start": 0, "end": 3, "weight": 3, "spoken_lo": 0, "spoken_hi": 3,
              "phone": "a b"}]
    strip_ranges(spans)
    assert sorted(spans[0]) == ["end", "phone", "start", "weight"]


def test_design_371_hand_out_drops_a_sound_no_token_owns():
    # `z` belongs to nobody. Forcing it onto a neighbour is what handed one
    # sentence's `The` seventy sounds.
    out = hand_out([["a", "b"], ["k"]], ["a", "b", "z", "k"])
    assert out == [["a", "b"], ["k"]]


def test_design_371_hand_out_keeps_the_order_and_does_not_overlap():
    out = hand_out([["a"], ["b"], ["c"]], ["a", "b", "c"])
    assert out == [["a"], ["b"], ["c"]]
    flat = [s for run in out for s in run]
    assert flat == ["a", "b", "c"]


def test_design_371_hand_out_gives_a_token_with_no_stencil_nothing():
    out = hand_out([["a"], [], ["c"]], ["a", "c"])
    assert out[1] == []


def test_design_371_the_key_moves_with_the_voice():
    one = cache_key("the film grew", "en-US-Neural2-D")
    two = cache_key("the film grew", "en-US-Neural2-F")
    assert one != two
    assert cache_key("the film grew", "en-US-Neural2-D") == one


def test_design_371_the_spoken_range_reconstructs_what_was_read():
    display = "The size grew from 2.3 nm after reduction."
    spoken = spoken_text_for_tts(display)
    report = align_display_report(display, spoken=spoken, with_spoken_range=True)
    assert report["code"] == "ok"
    said = {}
    for span in report["spans"]:
        lo, hi = span["spoken_lo"], span["spoken_hi"]
        assert 0 <= lo <= hi <= len(spoken)
        said[display[span["start"]:span["end"]]] = spoken[lo:hi]
    # This is the whole point of building the reference from the spoken form:
    # a printed `nm` is read as a word, not as two letters.
    assert said["nm"] == "nanometers"
    assert said["grew"] == "grew"


def test_design_371_the_spoken_ranges_move_forward_and_do_not_overlap():
    display = "A thin layer forms on the surface of the gold."
    spoken = spoken_text_for_tts(display)
    report = align_display_report(display, spoken=spoken, with_spoken_range=True)
    seen = -1
    for span in report["spans"]:
        assert span["spoken_lo"] >= seen
        seen = span["spoken_hi"]


def test_design_371_the_range_is_off_unless_asked_for():
    display = "The film grew at five hundred degrees."
    spoken = spoken_text_for_tts(display)
    plain = align_display_report(display, spoken=spoken)
    marked = align_display_report(display, spoken=spoken, with_spoken_range=True)
    # The highlight callers must keep the response they had.
    for span in plain["spans"]:
        assert sorted(span) == ["end", "start", "weight"]
    assert plain["code"] == marked["code"]
    assert [
        (s["start"], s["end"], s["weight"]) for s in plain["spans"]
    ] == [(s["start"], s["end"], s["weight"]) for s in marked["spans"]]
