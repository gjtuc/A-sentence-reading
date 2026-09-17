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
    out = spoken_text_for_tts("Ni(NO3)2 on the (110) facet").lower()
    assert "nickel" in out
    assert "nitrogen" in out and "oxygen" in out
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
