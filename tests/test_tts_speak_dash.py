# -*- coding: utf-8 -*-
"""design/217 — link hyphen ≠ minus for TTS spoken form."""
from __future__ import annotations

from sentence_reading.llm.tts_speak import spoken_text_for_tts
from sentence_reading.llm.tts_speak_policy import SPEAK_NORM_VERSION_DEFAULT


def test_speak_norm_v4() -> None:
    assert SPEAK_NORM_VERSION_DEFAULT == "v4"


def test_ni_cu_alloy_no_minus() -> None:
    out = spoken_text_for_tts("Ni-Cu alloy").lower()
    assert "minus" not in out
    assert "-" not in out
    assert "nickel" in out and "copper" in out


def test_f_t_synthesis_not_fluorine() -> None:
    out = spoken_text_for_tts("F-T synthesis").lower()
    assert "fluorine" not in out
    assert "minus" not in out
    assert "f" in out and "t" in out


def test_i_v_curve_letter_speak() -> None:
    out = spoken_text_for_tts("I-V curve").lower()
    assert "vanadium" not in out
    assert "minus" not in out
    assert "i" in out and "v" in out


def test_c_h_bond() -> None:
    out = spoken_text_for_tts("C-H bond").lower()
    assert "minus" not in out
    assert "c" in out and "h" in out


def test_n_doped() -> None:
    out = spoken_text_for_tts("N-doped carbon").lower()
    assert "minus" not in out
    assert "nitrogen" in out and "doped" in out


def test_units_cm_minus_one() -> None:
    assert "per centimeter" in spoken_text_for_tts("cm-1").lower()
    assert "per centimeter" in spoken_text_for_tts("cm\u22121").lower()
    assert "per centimeter" in spoken_text_for_tts(
        "1650 cm<sup>\u22121</sup>"
    ).lower()


def test_unary_minus_kept() -> None:
    out = spoken_text_for_tts("\u22125 \u00b0C").lower()
    assert "minus" in out
    assert "5" in out
    out2 = spoken_text_for_tts("x = -5").lower()
    assert "minus" in out2


def test_ph_and_wt_ranges_to() -> None:
    assert "to" in spoken_text_for_tts("pH 7-9").lower()
    assert "minus" not in spoken_text_for_tts("pH 7-9").lower()
    out = spoken_text_for_tts("15-20 wt%").lower()
    assert "to" in out
    assert "minus" not in out


def test_decade_10_3_not_range_to() -> None:
    out = spoken_text_for_tts("10-3 M").lower()
    assert "ten to three" not in out
    assert "to the minus" in out


def test_ft_ir() -> None:
    out = spoken_text_for_tts("FT-IR").lower()
    assert "fluorine" not in out
    assert "minus" not in out


def test_well_known_and_temper() -> None:
    assert "-" not in spoken_text_for_tts("well-known")
    out = spoken_text_for_tts("6061-T6").lower()
    assert "minus" not in out


def test_idempotent_dash_cases() -> None:
    for raw in ("Ni-Cu alloy", "F-T synthesis", "pH 7-9", "cm-1"):
        once = spoken_text_for_tts(raw)
        assert spoken_text_for_tts(once) == once
