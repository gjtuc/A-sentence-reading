# -*- coding: utf-8 -*-
"""design/205 — spoken-form aliases, acronyms, cache norm version."""
from __future__ import annotations

from sentence_reading.llm import tts as tts_mod
from sentence_reading.llm.tts_speak import spoken_text_for_tts
from sentence_reading.llm.tts_speak_policy import SPEAK_NORM_VERSION_DEFAULT


def test_chem_alias_ch4() -> None:
    out = spoken_text_for_tts("CH4 oxidation").lower()
    assert "four" in out


def test_chem_alias_h2o_unicode() -> None:
    out = spoken_text_for_tts("H₂O adsorption").lower()
    assert "two" in out


def test_nmr_letters() -> None:
    out = spoken_text_for_tts("The NMR spectrum shows").lower()
    assert "n m r" in out


def test_collapse_name_abbr() -> None:
    out = spoken_text_for_tts(
        "nuclear magnetic resonance (NMR) was used"
    ).lower()
    assert "nuclear magnetic resonance" in out
    assert "(nmr)" not in out
    assert "n m r" not in out


def test_fig_digit_not_chem() -> None:
    out = spoken_text_for_tts("as shown in Fig.2")
    assert "fig. two" not in out.lower()


def test_wh_still_not_tungsten() -> None:
    out = spoken_text_for_tts("750 Wh/L").lower()
    assert "watt hour per liter" in out
    assert "tungsten" not in out


def test_idempotent() -> None:
    raw = "CO2 and NMR peaks at 1650 cm-1"
    once = spoken_text_for_tts(raw)
    twice = spoken_text_for_tts(once)
    assert once == twice


def test_prosody_arrow_comma() -> None:
    out = spoken_text_for_tts("A → B")
    assert "goes to," in out.lower()


def test_cache_key_includes_norm_version() -> None:
    assert SPEAK_NORM_VERSION_DEFAULT == "v3"
    k1 = tts_mod.cache_key("hello", "en-US-Neural2-D", 1.0)
    assert len(k1) == 24


def test_cite_sup_not_spoken_as_number() -> None:
    """design/216 — strip <sup>n</sup> before HTML spoken (no 'twelve')."""
    out = spoken_text_for_tts("major contributors.<sup>12</sup>").lower()
    assert "twelve" not in out
    assert "contributors" in out


def test_unit_sup_still_spoken() -> None:
    out = spoken_text_for_tts("peak at 1650 cm<sup>−1</sup>").lower()
    assert "per centimeter" in out or "centimeter" in out
