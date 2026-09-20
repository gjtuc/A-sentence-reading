"""design/342 — a hyphen inside a sample code is not a minus and not a range.

Ranking the chemical tokens that still produced defective speech put a sample code
at the top, not a compound name: `BZY10-1700` appears 32 times in one paper and was
read as "B Z Y 10 **minus** 1700". The linter never flagged it, because it has no
check for a wrongly voiced dash — the corpus token ranking found it.

Two rules had to move, since silencing one exposed the other:

1. `_dash_pass_a` reads a hyphen before a digit as a unary minus. After `freeze`
   the left neighbour is a placeholder, which is not alphanumeric, so the guard
   that was meant to protect mid-token hyphens did not fire.
2. With the minus gone, a later range rule said "B Z Y 10 **to** 1700". The hyphen
   is now silenced in `restore`, where the placeholder proves the two halves belong
   to one name — which is how `BZY10-ZnO` has always read.
"""

from __future__ import annotations

from sentence_reading.llm.tts_speak import spoken_text_for_tts as say


# ------------------------------------------------- the code


def test_a_sample_code_with_a_number_suffix() -> None:
    out = say("The BZY10-1700 sample was sintered at high temperature.")
    assert "minus" not in out
    assert " to " not in out
    assert "B Z Y 10 1700" in out


def test_two_codes_in_one_sentence() -> None:
    out = say("BZY10-1650 and BZY10-1700 were compared.")
    assert "minus" not in out
    assert out.count("B Z Y 10") == 2


def test_a_code_with_a_formula_suffix_still_reads() -> None:
    """`BZY10-ZnO` already worked; it must keep working."""
    assert "zinc oxide" in say("BZY10-ZnO was measured.")
    assert "minus" not in say("BZY10-ZnO was measured.")


def test_other_code_shapes_are_unchanged() -> None:
    out = say("ZIF-8 and CM-95 were used.")
    assert "Z I F 8" in out
    assert "C M 95" in out
    assert "minus" not in out


# ------------------------------------------------- what must still be a minus


def test_a_negative_number_is_still_minus() -> None:
    assert "minus 70" in say("Delta H was -70 kJ/mol.")
    assert "minus 0.5" in say("a value of -0.5 V was applied")


def test_a_decade_power_is_still_an_inverse() -> None:
    assert "minus" in say("the 10-3 decade power")


# ------------------------------------------------- what must still be a range


def test_a_printed_range_still_says_to() -> None:
    assert "10 to 1700" in say("the range was 10-1700 K")
    assert "500 to 700" in say("the temperature range 500-700 K")
    assert "4 to 7" in say("pH 4-7 was tested")
    assert "30 to 40" in say("30-40 wt% loading")
    assert "2011 to 2015" in say("a 2011-2015 study")


def test_a_range_after_a_frozen_token_still_says_to() -> None:
    """The guard keys on the placeholder, not on "a number came before"."""
    assert "500 to 700" in say("H2 uptake was measured over 500-700 K")


def test_a_decimal_range_still_says_to() -> None:
    assert "1.08 to 2.15" in say("a value of 1.08-2.15 mm")
    assert "0.5 to 1.5" in say("swept from 0.5-1.5 V")


def test_a_spaced_range_still_says_to() -> None:
    assert "10 to 20" in say("from 10 - 20 K")


# ------------------------------------------------- grant numbers


def test_a_grant_number_is_not_a_range() -> None:
    """The linter's new check found this one: "award DMR 08 to 019762"."""
    out = say("The research was supported under award DMR 08-019762.")
    assert " to " not in out


def test_a_leading_zero_marks_a_code_only_for_integers() -> None:
    """`0.5` is a decimal, not a code, so it must not be treated as one."""
    assert "0.5 to 1.5" in say("swept from 0.5-1.5 V")
    assert " to " not in say("grant 2019-0123 funded the work")


# ------------------------------------------------- link hyphens


def test_element_and_technique_hyphens_are_unchanged() -> None:
    assert "iron nickel" in say("the Fe-Ni alloy was stable")
    assert "hydrogen t p r" in say("H2-TPR was applied.").lower()
    assert "nitrogen doped" in say("N-doped carbon").lower()


def test_still_idempotent() -> None:
    for text in (
        "The BZY10-1700 sample was sintered.",
        "the range was 10-1700 K",
        "Delta H was -70 kJ/mol.",
    ):
        once = say(text)
        assert say(once) == once, text
