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

def _seed(tmp_path, monkeypatch, display: str):
    """Write the reference the route will look for, so no voice is needed."""
    import json

    from sentence_reading.llm import sound_reference as sr

    monkeypatch.setenv("ASR_SOUND_REF_DIR", str(tmp_path))
    monkeypatch.setenv("ASR_SOUND_REF", "1")
    monkeypatch.setenv("ASR_ACCESS_GATE", "0")
    spoken = spoken_text_for_tts(display)
    words = []
    for m in __import__("re").finditer(r"\S+", spoken):
        words.append({"lo": m.start(), "hi": m.end(),
                      "sounds": " ".join(list(m.group(0).lower()))[:40]})
    got = {"voice": sr.reference_voice(), "words": words,
           "natural_n": 0, "mark_n": len(words)}
    key = sr.cache_key(spoken, sr.reference_voice())
    (tmp_path / f"{key}.json").write_text(
        json.dumps(got, ensure_ascii=False), encoding="utf-8"
    )
    return spoken


def test_design_371_the_route_serves_a_cached_reference(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from sentence_reading.api.app import app

    display = "The film grew at five hundred degrees."
    _seed(tmp_path, monkeypatch, display)
    got = TestClient(app).post("/api/tts/spoken", json={"text": display}).json()
    assert got["ok"] is True
    assert got["sound_ref_code"] == "ready"
    assert got["sound_ref_n"] > 0
    # The wire format keeps the four keys the client parses, and nothing else.
    for span in got["spans"]:
        assert sorted(span) == ["end", "phone", "start", "weight"]
    # grew is spelled the same spoken and printed, so the seeded sounds land.
    by = {display[s["start"]:s["end"]]: s["phone"] for s in got["spans"]}
    assert by["grew"] == "g r e w"


def test_design_371_the_kill_switch_leaves_the_old_behaviour(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from sentence_reading.api.app import app

    display = "The film grew at five hundred degrees."
    _seed(tmp_path, monkeypatch, display)
    monkeypatch.setenv("ASR_SOUND_REF", "0")
    monkeypatch.setenv("ASR_SOUND_REF_DIR", str(tmp_path / "empty"))
    got = TestClient(app).post("/api/tts/spoken", json={"text": display}).json()
    assert got["ok"] is True
    assert got["sound_ref_code"] == "off"
    # design/368 behaviour: the key is present and empty, never missing.
    assert all(span["phone"] == "" for span in got["spans"])


def test_design_371_a_reference_for_another_sentence_is_not_used(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from sentence_reading.api.app import app

    from sentence_reading.llm import sound_reference as sr

    _seed(tmp_path, monkeypatch, "The film grew at five hundred degrees.")
    # A real build would reach a voice and the model on a background thread and
    # go on running through the rest of the suite. Only the asking is under test.
    asked: list[str] = []
    monkeypatch.setattr(sr, "build", lambda spoken, **kw: asked.append(spoken))
    other = "A thin layer forms on the surface of the gold."
    got = TestClient(app).post("/api/tts/spoken", json={"text": other}).json()
    assert got["ok"] is True
    # Content-addressed, so a different sentence misses and is asked for.
    assert got["sound_ref_code"] in ("queued", "building", "busy")
    assert got["sound_ref_n"] == 0


def test_design_371_a_build_that_keeps_failing_stops_being_asked_for(
        tmp_path, monkeypatch):
    from sentence_reading.llm import sound_reference as sr

    # A failed build still costs a synthesis call, so a voice we cannot use would
    # bill us once per sentence opened, forever.
    monkeypatch.setattr(sr, "_BUILD_RUN", sr.BUILD_GIVE_UP)
    monkeypatch.setenv("ASR_SOUND_REF", "1")
    monkeypatch.setenv("ASR_SOUND_REF_DIR", str(tmp_path))
    assert sr.request_build("the film grew") == "sunk"
    monkeypatch.setattr(sr, "_BUILD_RUN", sr.BUILD_GIVE_UP - 1)
    asked: list[str] = []
    monkeypatch.setattr(sr, "build", lambda spoken, **kw: asked.append(spoken))
    assert sr.request_build("the film grew") == "queued"


def test_design_371_a_stencil_that_misheard_does_not_cost_the_word_its_sounds():
    # Read alone, the model heard 	hin as the sounds of 	hen. Matching on
    # identity with free skips left the word with one sound out of three, which
    # put it under design/366's floor and stopped it being judged at all.
    out = hand_out([["d", "e", "n"]], ["th", "i", "n"])
    assert out == [["th", "i", "n"]]


def test_design_371_a_sound_the_stencil_missed_still_goes_to_its_word():
    # The isolated reading of ilm dropped the closing m, but the straight
    # reading has it, and it belongs to ilm rather than to nobody.
    out = hand_out([["f", "i", "l"], ["g", "r", "u"]],
                   ["f", "i", "l", "m", "g", "r", "u"])
    assert out == [["f", "i", "l", "m"], ["g", "r", "u"]]


def test_design_371_the_key_moves_with_the_cutting_rule():
    # A reference built under an older skip cost is a different reference, and
    # GCS keeps them for months.
    import sentence_reading.llm.sound_reference as sr

    before = sr.cache_key("the film grew", "en-US-Neural2-D")
    old = sr.SKIP_COST
    try:
        sr.SKIP_COST = old + 0.1
        after = sr.cache_key("the film grew", "en-US-Neural2-D")
    finally:
        sr.SKIP_COST = old
    assert before != after
