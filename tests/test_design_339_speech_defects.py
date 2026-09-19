"""design/339 — fix what the speech linter found, measured on ten papers.

`agent-tools/speak_lint.py` flags spoken output carrying the signature of a known
failure mode. Run over 2,366 sentences from the ten-paper corpus it reported 224
defective sentences. The families it named were symptoms; grouped by cause they were
five bugs, and the worst made sentences say the wrong thing:

    Fig. S1              -> "figure sulfur 1"
    <i>K</i><sub>obs</sub> -> "potassium o b s"
    where <i>C</i> is     -> "where carbon is"
    t<sub>ion</sub>       -> "t i o n"
    &gt;                  -> ">"

After this chip the corpus reports 99. What remains is listed in the design doc as
separate work, not as a claim of completeness.
"""

from __future__ import annotations

from sentence_reading.llm.tts_speak import spoken_text_for_tts as say


# ------------------------------------------------- a subscript that is a word


def test_an_abbreviated_subscript_is_a_word_not_letters() -> None:
    out = say("The <i>K</i><sub>obs</sub> was 0.0717 min<sup>-1</sup>.")
    assert "o b s" not in out
    assert "observed" in out


def test_a_pronounceable_subscript_falls_back_to_itself() -> None:
    out = say("t<sub>ion</sub> of the bulk conduction decreases.")
    assert "i o n" not in out
    assert "ion" in out


def test_an_orbital_label_is_still_spelled() -> None:
    """design/326 chose `e g` and `t two g` deliberately; keep them."""
    assert "e g" in say("The <i>e<sub>g</sub></i> filling governs activity.")
    assert "b" in say("Here d<sub>gb</sub> is assumed to be 10 nm.")


def test_a_consonant_only_subscript_is_still_spelled() -> None:
    out = say("The d<sub>gb</sub> thickness was measured.")
    assert "g b" in out


# ------------------------------------------------- italics mark a variable


def test_an_italic_letter_is_not_an_element() -> None:
    out = say("where <i>C</i> is the concentration of the anion")
    assert "carbon" not in out
    assert "C is the concentration" in out


def test_an_italic_variable_with_a_subscript() -> None:
    out = say("The <i>K</i><sub>obs</sub> values were compared.")
    assert "potassium" not in out


def test_a_formula_letter_is_still_an_element() -> None:
    """Only italics make it a variable; plain formulas must still be named."""
    assert "carbon dioxide" in say("We measured CO2 uptake.").lower()
    assert "nitrogen" in say("N<sub>2</sub> adsorption isotherms.").lower()


# ------------------------------------------------- supplementary labels


def test_a_supplementary_figure_label_is_not_sulfur() -> None:
    out = say("TEM images are shown in Fig. S1 in the supplementary information.")
    assert "sulfur" not in out
    assert "figure S1" in out


def test_a_range_of_supplementary_labels() -> None:
    """`Figs. S1 to S7` — only the first S has a label word in front of it."""
    out = say("Figs. S1 to S7 and Tables S1 to S5 are provided.")
    assert "sulfur" not in out
    assert "Figures" in out


def test_sulfur_is_still_sulfur_without_a_supplementary_context() -> None:
    out = say("We added S8 powder and measured SO2 release.")
    assert "sulfur" in out


# ------------------------------------------------- abbreviations and symbols


def test_plural_figure_abbreviation_is_not_a_fruit() -> None:
    out = say("See Fig. 3 and Figs. 4 and Eqs. 2.")
    assert "Figs" not in out
    assert "figures" in out
    assert "equations" in out


def test_an_angle_bracket_is_a_comparison() -> None:
    out = say("The order was BZY10-ZnO &gt; BZY10-1650.")
    assert ">" not in out
    assert "greater than" in out


def test_a_prose_slash_is_two_words() -> None:
    out = say("N<sub>2</sub> adsorption/desorption isotherms were measured.")
    assert "/" not in out
    assert "adsorption, desorption" in out


def test_a_url_is_left_alone_rather_than_mangled() -> None:
    """A link is not practice speech; breaking it up would only hide that."""
    out = say("To view a copy of this license, visit http://creativecommons.org/licenses/by/4.0/")
    assert "creativecommons.org/licenses" in out


# ------------------------------------------------- units and greek subscripts


def test_molar_concentrations_are_spoken() -> None:
    out = say("The concentration dropped from ~0.4 mM to below 1 ppb.")
    assert "millimolar" in out
    assert "parts per billion" in out
    assert "parts per million" in say("A residue of 51 ppm remained.")


def test_seconds_abbreviation_is_spoken() -> None:
    assert "seconds" in say("The contact time was only ~35 sec.")


def test_a_greek_letter_in_a_subscript_is_resolved() -> None:
    out = say(
        "We found that Ba<sub>0.5</sub>Sr<sub>0.5</sub>Co<sub>0.8</sub>"
        "Fe<sub>0.2</sub>O<sub>3-\u03b4</sub> catalyzes the reaction."
    )
    assert "3-" not in out
    assert "three minus delta" in out


# ------------------------------------------------- nothing already right broke


def test_known_good_forms_are_unchanged() -> None:
    assert "water" in say("H2O was formed.").lower()
    assert "kelvin" in say("The run was at 500 K.")
    assert "hours" in say("It ran for 2 h.")
    assert "palladium on alumina" in say("Pd/Al<sub>2</sub>O<sub>3</sub> was used.").lower()
    assert "B site" in say("The B site cation controls activity.")
    assert "B sites" in say("The B sites are occupied.")


def test_the_transform_is_still_idempotent() -> None:
    for text in (
        "The <i>K</i><sub>obs</sub> for SP20 was 0.0717 min<sup>-1</sup>.",
        "Fig. S1 shows N<sub>2</sub> adsorption/desorption at 0.4 mM.",
        "NMR and F-T synthesis of H2SO4 at 500 K.",
    ):
        once = say(text)
        assert say(once) == once, text
