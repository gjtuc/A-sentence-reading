"""design/341 — a unit run is grammar, and a slash between symbols is a ratio.

design/339 left 83 speech defects. The two biggest families had one cause each, and
the unit one was not merely unnatural — it was **wrong**:

    259.1 m²·g⁻¹  ->  "259.1 m times per gram"

The `2` was deleted by design/216's citation stripper, exactly the class design/328
fixed for orbital exponents but never for units, so an area per mass was read out as
a length per mass. And `·` was mapped to " times " globally, though inside a unit
product it separates rather than multiplies.

The slash family was 38 hits dominated by one repeated phrase: `STY CH4/STY CO2`,
spoken with the slash intact seven times in a single paper.
"""

from __future__ import annotations

from sentence_reading.llm.tts_speak import spoken_text_for_tts as say


# ------------------------------------------------- the exponent that was deleted


def test_a_positive_unit_exponent_survives() -> None:
    out = say("The BET area was ~259.1 m<sup>2</sup>\u00b7g<sup>-1</sup>.")
    assert "square meters per gram" in out
    assert "times" not in out


def test_a_cubic_unit() -> None:
    out = say("The pore volume was ~0.4208 cm<sup>3</sup>\u00b7g<sup>-1</sup>.")
    assert "cubic centimeters per gram" in out


def test_a_three_part_unit_run() -> None:
    out = say("The loading rate was ~2.83 L\u00b7m<sup>-2</sup>\u00b7s<sup>-1</sup>.")
    assert "liters per square meter per second" in out


def test_a_slash_inside_a_unit_run_is_per() -> None:
    assert "milliliters per minute" in say("a rate of 12 mL/min was used")
    assert "kilojoules per mole" in say("a value of 45 kJ/mol was found")


def test_unicode_superscripts_work_too() -> None:
    assert "square meters per gram" in say("an area of 259.1 m\u00b2\u00b7g\u207b\u00b9")


# ------------------------------------------------- plain abbreviations


def test_plain_abbreviations_that_were_left_to_tts() -> None:
    assert "millimeters" in say("inner diameter of 10 mm")
    assert "grams" in say("Typically, 0.2 g of catalysts were diluted.")
    assert "liters" in say("a volume of 5 L was used")


def test_what_already_worked_still_works() -> None:
    assert "per centimeter" in say("band at 800 cm-1").lower()
    assert "kelvin" in say("The run was at 500 K.")
    assert "hours" in say("It ran for 2 h.")
    assert "minutes" in say("for 45 min reaction")
    assert "kilograms" in say("in 50 kg water")


# ------------------------------------------------- what must not be a unit


def test_an_orbital_subscript_is_not_grams() -> None:
    """`<sub>2g</sub>` is design/328's orbital label; `g` nearly ate it."""
    out = say("The <i>t<sub>2g</sub></i><sup>5</sup> configuration is filled.")
    assert "gram" not in out
    assert "t two g" in out


def test_an_orbital_after_an_element_is_not_seconds() -> None:
    """`O 1s` would become "1 seconds" if `s` were a plain unit token."""
    out = say("The O 1s and Fe 2p peaks were fitted.")
    assert "second" not in out


def test_a_plain_number_is_not_a_unit() -> None:
    assert say("Table 4 summarizes 3 samples.") == "Table 4 summarizes 3 samples."
    assert "meter" not in say("Figure 6 shows 2 peaks.")


# ------------------------------------------------- the slash


def test_a_ratio_of_formulas_is_over() -> None:
    out = say(
        "Figure 6 shows the variation of STY<sub>CH<sub>4</sub></sub>/"
        "STY<sub>CO<sub>2</sub></sub> with temperature."
    )
    assert "/" not in out
    assert "over" in out


def test_a_prose_slash_is_still_a_pause() -> None:
    out = say("N<sub>2</sub> adsorption/desorption isotherms.")
    assert "adsorption, desorption" in out
    assert "over" not in out


def test_a_url_keeps_its_slashes() -> None:
    out = say("visit http://creativecommons.org/licenses/by/4.0/")
    assert "creativecommons.org/licenses/by/4.0/" in out
    assert "over" not in out


# ------------------------------------------------- reporting and stability


def test_the_rsc_page_stamp_is_back_matter() -> None:
    from sentence_reading.llm.debone_quality import is_back_matter_sentence

    assert is_back_matter_sentence("Downloaded on 5/28/2026 1:22:30 AM.") is True
    assert is_back_matter_sentence("The sample was downloaded twice.") is False


def test_still_idempotent() -> None:
    for text in (
        "The BET area was ~259.1 m<sup>2</sup>\u00b7g<sup>-1</sup>.",
        "a rate of 12 mL/min at 500 K for 2 h",
        "STY<sub>CH<sub>4</sub></sub>/STY<sub>CO<sub>2</sub></sub> stayed above unity.",
    ):
        once = say(text)
        assert say(once) == once, text
