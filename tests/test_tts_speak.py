# -*- coding: utf-8 -*-
"""design/88 — spoken_text_for_tts polish."""
from __future__ import annotations

from sentence_reading.llm.tts_speak import spoken_text_for_tts


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


def test_title_prefix_stripped() -> None:
    out = spoken_text_for_tts("Title: Nickel catalyst")
    assert not out.lower().startswith("title")
    assert "nickel" in out.lower()
