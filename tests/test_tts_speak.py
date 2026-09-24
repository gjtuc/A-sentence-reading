# -*- coding: utf-8 -*-
"""design/88+90 — spoken_text_for_tts polish · unit lexicon."""
from __future__ import annotations

from sentence_reading.llm.tts_speak import spoken_text_for_tts


def test_wh_per_liter_not_tungsten() -> None:
    """design/90 — W h L⁻¹ is energy density, not tungsten."""
    for raw in (
        "2800 W h L<sup>-1</sup>",
        "2800 W h L⁻¹",
        "750 Wh/L",
        "750 W h / L",
    ):
        out = spoken_text_for_tts(raw).lower()
        assert "watt hour per liter" in out
        assert "tungsten" not in out


def test_mah_per_gram() -> None:
    out = spoken_text_for_tts("150 mAh g⁻¹").lower()
    assert "milliampere hour per gram" in out


def test_kj_per_mole() -> None:
    out = spoken_text_for_tts("100 kJ mol<sup>−1</sup>").lower()
    assert "kilojoule per mole" in out


def test_bare_watt_after_digit() -> None:
    out = spoken_text_for_tts("rated at 100 W").lower()
    assert "watt" in out
    assert "tungsten" not in out


def test_sub_html_spoken() -> None:
    out = spoken_text_for_tts("H<sub>2</sub>O")
    assert "sub" not in out.lower()
    assert "hydrogen" in out.lower() or "H" not in out  # Ni-style expand may hit H
    # At least digits spoken and no raw tags
    assert "2" not in out or "two" in out


def test_escaped_sub_not_spoken_as_tag() -> None:
    out = spoken_text_for_tts("H&lt;sub&gt;2&lt;/sub&gt;O")
    assert "<" not in out
    assert "sub" not in out.lower()


def test_cm_inverse_unit() -> None:
    out = spoken_text_for_tts("peak at 1650 cm<sup>−1</sup>")
    assert "per centimeter" in out.lower()
    assert "sub" not in out.lower()


def test_plain_cm_minus_one() -> None:
    out = spoken_text_for_tts("band at 800 cm-1")
    assert "per centimeter" in out.lower()


def test_reaction_arrow() -> None:
    out = spoken_text_for_tts("A → B")
    assert "goes to" in out.lower()


def test_equilibrium_arrow() -> None:
    out = spoken_text_for_tts("A ⇌ B")
    assert "equilibrium" in out.lower()


def test_cite_markers_stripped_for_tts() -> None:
    out = spoken_text_for_tts(
        "Methane and CO2 are major GHG contributors.[1-4]"
    )
    assert "[" not in out
    assert "1-4" not in out
    assert "contributors" in out.lower()


def test_plain_trailing_acs_cite_stripped_for_tts() -> None:
    minus = "\u2212"
    out = spoken_text_for_tts(f"Ni nanoparticles for the MDR reaction.6{minus}9")
    assert minus not in out
    assert out.endswith("reaction.")
    assert ".6" not in out


def test_title_prefix_stripped() -> None:
    out = spoken_text_for_tts("Title: Nickel catalyst")
    assert not out.lower().startswith("title")
    assert "nickel" in out.lower()


def test_parenthetical_aside_is_not_spoken() -> None:
    out = spoken_text_for_tts(
        "The catalyst (see Fig. 1) was stable (e.g., after 10 h)."
    ).lower()
    assert "fig" not in out
    assert "e.g" not in out
    assert "after 10" not in out
    assert "catalyst" in out and "stable" in out
    assert spoken_text_for_tts(out) == out


def test_formula_parentheses_stay_in_speech() -> None:
    """design/326 — Ni(NO3)2 is nickel nitrate.

    This used to assert 'nitrogen' and 'oxygen', locking in a name composed from
    parts. No chemist says 'nickel nitrogen oxygen three two'.
    """
    out = spoken_text_for_tts("Ni(NO3)2 on the (110) facet").lower()
    assert "nickel nitrate" in out
    assert "nitrogen" not in out
    assert "110" in out
    assert "(" not in out


def test_common_names_beat_element_spellout() -> None:
    co2 = spoken_text_for_tts("CO2 reduction").lower()
    assert "carbon dioxide" in co2
    assert "vanadium" not in co2
    ch4 = spoken_text_for_tts("CH3COOH yields").lower()
    assert "acetic acid" in ch4
    assert "methyl" not in ch4


def test_formula_fragment_name_when_whole_is_unknown() -> None:
    out = spoken_text_for_tts("RCOOH oxidation").lower()
    assert "carboxyl" in out
    assert "carbon oxygen" not in out


def test_unknown_all_caps_is_letters_not_elements() -> None:
    out = spoken_text_for_tts("grown by CVD and ALD").lower()
    assert "c v d" in out
    assert "a l d" in out
    assert "carbon" not in out
    assert "vanadium" not in out
    assert "aluminum" not in out


def test_duplicate_formula_paren_is_not_spoken_twice() -> None:
    out = spoken_text_for_tts("carbon dioxide (CO2) evolved").lower()
    assert out.count("carbon dioxide") == 1
    aside = spoken_text_for_tts(
        "The yield (n = 3) rose (after 10 h)."
    ).lower()
    assert "n =" not in aside and "after 10" not in aside
    assert "yield" in aside and "rose" in aside


def test_follow_spans_cover_common_name_and_letters() -> None:
    from sentence_reading.llm.tts_speak import align_display_to_spoken

    co2 = align_display_to_spoken("CO2 reduction")
    assert co2
    co2_span = next(s for s in co2 if s["weight"] > 0)
    assert co2_span["start"] == 0
    assert co2_span["end"] == 3
    assert co2_span["weight"] > 3

    cvd = align_display_to_spoken("grown by CVD")
    lit = [s for s in cvd if s["weight"] > 0]
    assert lit[-1]["start"] == "grown by CVD".index("CVD")
    assert lit[-1]["end"] == lit[-1]["start"] + 3

    aside = align_display_to_spoken("The yield (n = 3) rose")
    assert aside
    n_span = next(s for s in aside if s["start"] == aside_text_index("The yield (n = 3) rose"))
    assert n_span["weight"] == 0


def aside_text_index(text: str) -> int:
    return text.index("n")


def test_align_display_report_is_counts_and_code_only() -> None:
    from sentence_reading.llm.tts_speak import align_display_report

    empty = align_display_report("   ")
    assert empty["code"] == "empty_display"
    assert empty["spans"] == []
    assert "text" not in empty

    period = align_display_report("CVD is a technique.")
    assert period["code"] == "ok"
    assert period["spans"]
    assert period["cursor"] == period["spoken_chars"]
    assert set(period) == {
        "code",
        "spans",
        "token_i",
        "cursor",
        "display_chars",
        "spoken_chars",
        "token_len",
        "piece_len",
        "differ_at",
        "token_shape",
        "piece_class",
        "full_class",
        "gap_len",
        "gap_shape",
        "matched_n",
        "tail_n",
        "renamed_n",
    }


def test_unmatched_token_keeps_earlier_words() -> None:
    from sentence_reading.llm.tts_speak import align_display_report

    report = align_display_report("the cat sat", spoken="the cat")
    assert report["code"] == "token_unmatched"
    kept = [
        s
        for s in report["spans"]
        if s["weight"] > 0 and s["end"] > s["start"]
    ]
    assert kept
    assert kept[0]["start"] == 0
    assert report["matched_n"] == len(kept)
    assert report["tail_n"] >= 1
    assert report["token_shape"] in {"letters", "digits", "alnum", "apos", "other"}
    assert "text" not in report
    blob = str({k: v for k, v in report.items() if k != "spans"})
    assert "cat" not in blob


def test_a_renamed_word_keeps_the_rest_of_the_sentence() -> None:
    from sentence_reading.llm.tts_speak import align_display_report

    report = align_display_report(
        "size of approximately 1 nm, which is substantially smaller than"
    )
    assert report["code"] == "ok"
    assert report["renamed_n"] >= 1
    assert report["tail_n"] == 0
    kept = [s for s in report["spans"] if s["weight"] > 0 and s["end"] > s["start"]]
    assert len(kept) == 10


def test_pt_case_does_not_drop_the_tail() -> None:
    from sentence_reading.llm.tts_speak import align_display_report

    report = align_display_report(
        "Chemical vapor deposition of highly dispersed Pt nanoparticles"
    )
    assert report["code"] == "ok"
    assert report["matched_n"] == 8
    assert report["tail_n"] == 0


def test_comma_between_words_does_not_drop_the_tail() -> None:
    from sentence_reading.llm.tts_speak import align_display_report

    report = align_display_report("ant is happy, for rabbits birthday.")
    kept = [
        s
        for s in report["spans"]
        if s["weight"] > 0 and s["end"] > s["start"]
    ]
    assert report["code"] == "ok"
    assert report["tail_n"] == 0
    assert len(kept) == 6


def test_spoken_align_evidence_omits_sentence_text(monkeypatch) -> None:
    captured: dict = {}

    def _capture(kind, **kwargs):
        captured["kind"] = kind
        captured["code"] = kwargs.get("code")
        captured["details"] = kwargs.get("details")

    import sentence_reading.llm.evidence_bus as eb

    monkeypatch.setattr(eb, "emit", _capture)
    from sentence_reading.api.routes.tts import _emit_spoken_align
    from sentence_reading.llm.tts_speak import align_display_report

    raw = "CVD is a technique."
    report = align_display_report(raw)
    spans = report["spans"] if report["code"] == "ok" else []
    _emit_spoken_align({"cache_id": "c1", "text": raw}, "c v d is a technique", report, spans)
    blob = str(captured)
    assert "CVD" not in blob
    assert "technique" not in blob
    assert captured["kind"] == "practice_skill_align"
    assert captured["code"] == "ok"
    assert captured["details"]["phase"] == "server_align"
    assert captured["details"]["span_n"] == len(spans)
    assert captured["details"]["spoken_chars"] == len("c v d is a technique")
    assert captured["details"]["token_shape"] == "none"
    assert captured["details"]["tail_n"] == 0


def test_phone_assign_records_a_count_mismatch(monkeypatch) -> None:
    from sentence_reading.llm import phone_match as pm

    monkeypatch.setattr(pm.shutil, "which", lambda _name: "espeak-ng")
    monkeypatch.setattr(pm, "espeak_ipa_words", lambda _text: ["s əʊ", "f ɑː", "extra"])
    phones, report = pm.phone_assign("So far", [2, 3])
    assert report["phone_code"] == "count_mismatch"
    assert report["phone_word_n"] == 2
    assert report["phone_ipa_n"] == 3
    assert phones == ["", ""]
