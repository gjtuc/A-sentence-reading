"""design/392 - a spoken word nobody printed must not slide the later words."""

from __future__ import annotations

from sentence_reading.llm.tts_speak import align_display_report, spoken_text_for_tts


def _pairs(display: str) -> tuple[dict, list[tuple[str, str]]]:
    spoken = spoken_text_for_tts(display)
    rep = align_display_report(display, spoken=spoken, with_spoken_range=True)
    pairs = [
        (display[s["start"]:s["end"]], spoken[s["spoken_lo"]:s["spoken_hi"]])
        for s in rep["spans"]
        if "spoken_lo" in s
    ]
    return rep, pairs


def test_slash_read_as_on_does_not_slide_the_tail() -> None:
    rep, pairs = _pairs("the surface area of Pt/CNT prepared by CVD")
    assert rep["code"] == "ok"
    assert rep["inserted_n"] == 1
    got = dict(pairs[-4:])
    assert got["CNT"] == "on C N T"
    assert got["prepared"] == "prepared"
    assert got["by"] == "by"
    assert got["CVD"] == "C V D"


def test_markup_names_are_not_words() -> None:
    rep, pairs = _pairs("O<sub>2</sub> adsorption was then conducted")
    assert rep["code"] == "ok"
    words = [w for w, _ in pairs]
    assert "sub" in words
    for word, said in pairs:
        if word == "sub":
            assert said == ""
    assert dict(pairs)["adsorption"] == "adsorption"


def test_markup_spans_weigh_nothing() -> None:
    rep, _ = _pairs("the <i>p</i>O<sub>2</sub> transition")
    for span in rep["spans"]:
        if span.get("weight") == 0 and span.get("end", 0) > span.get("start", 0):
            break
    else:
        raise AssertionError("no zero-weight markup span")


def test_a_skipped_to_match_has_to_end_at_a_word_edge() -> None:
    from sentence_reading.llm.tts_speak import _match_past_inserted

    full = "of platinum on CVD prepared"
    # `C` would match the front of `CVD`; it is not a word there.
    assert _match_past_inserted(full, len("of platinum"), "C") is None
    assert _match_past_inserted(full, len("of platinum"), "CVD") == len(
        "of platinum on CVD"
    )


def test_a_plain_sentence_is_untouched() -> None:
    rep, pairs = _pairs("The cubic phase displays an increased density")
    assert rep["code"] == "ok"
    assert rep["inserted_n"] == 0
    assert all(w == s for w, s in pairs)
