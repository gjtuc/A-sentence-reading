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
