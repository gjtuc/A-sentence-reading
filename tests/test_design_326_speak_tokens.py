"""design/326 — practice-mode speech: one token, one decision.

Assertions are semantic, not exact strings, so wording can improve without the
file becoming a wall of churn. Every case here came from a real paper.
"""

from __future__ import annotations

from sentence_reading.llm.speak_tokens import (
    compound_name,
    letter_spell,
    voice_definitions,
)
from sentence_reading.llm.tts_speak import spoken_text_for_tts
from sentence_reading.llm.tts_speak_policy import (
    SPEAK_NORM_VERSION_DEFAULT,
    load_speak_policy,
)


def _s(raw: str) -> str:
    return spoken_text_for_tts(raw)


# --- P3: an acronym is atomic, plural s included -------------------------------


def test_plural_acronym_is_not_split_into_elements():
    """The bug that started this: one trailing `s` exposed C and N."""
    for raw, want in (
        ("CNTs", "C N Ts"),
        ("CVDs", "C V Ds"),
        ("SACs", "S A Cs"),
        ("NPs", "N Ps"),
        ("MEAs", "M E As"),
        ("RDSs", "R D Ss"),
    ):
        got = _s(raw)
        assert got == want, f"{raw} -> {got}"
        low = got.lower()
        for element in ("carbon", "nitrogen", "sulfur", "vanadium", "phosphorus"):
            assert element not in low, f"{raw} leaked {element}"


def test_singular_and_plural_acronyms_agree():
    assert _s("CNT") == "C N T"
    assert _s("CNTs") == "C N Ts"


def test_acronym_casing_survives_for_prosody():
    out = _s("DRM has the lowest operating cost")
    assert out.startswith("D R M")


def test_letter_spell_keeps_the_plural():
    assert letter_spell("CNT") == "C N T"
    assert letter_spell("CNTs") == "C N Ts"


# --- P1/P2: never compose a chemical name from parts ---------------------------


def test_binary_oxides_get_their_real_name():
    for raw, want in (
        ("NiO", "nickel oxide"),
        ("Fe2O3", "iron oxide"),
        ("IrO2", "iridium oxide"),
    ):
        got = _s(raw).lower()
        assert want in got, f"{raw} -> {got}"
        assert "oxygen" not in got, f"{raw} composed a name: {got}"


def test_acids_and_salts_get_their_real_name():
    assert "nitric acid" in _s("HNO3").lower()
    assert "nickel nitrate" in _s("Ni(NO3)2").lower()
    assert "magnesium aluminate" in _s("MgAl2O4").lower()
    assert "magnetite" in _s("Fe3O4").lower()


def test_unnameable_formula_is_spelled_not_invented():
    """Three or more elements has no name a reader expects. Spell it."""
    for raw in ("LaNiO3", "NiCo2O4", "FeOx"):
        got = _s(raw)
        assert "oxygen" not in got.lower(), f"{raw} -> {got}"
        # Spelled symbols: single capitals separated by spaces.
        assert got.split()[0].isupper()


def test_compound_name_returns_none_rather_than_guessing():
    assert compound_name("NiO") == "nickel oxide"
    assert compound_name("LaNiO3") is None
    assert compound_name("FeOx") is None


# --- P3: a lattice position is not an element ---------------------------------


def test_site_label_is_not_an_element():
    for raw in ("B-site", "the B site", "B'-site"):
        got = _s(raw).lower()
        assert "boron" not in got, f"{raw} -> {got}"
        assert "site" in got


def test_a_site_still_works():
    assert "a site" in _s("A-site cations").lower()


# --- P4: voice the definition and the abbreviation ----------------------------


def test_definition_and_abbreviation_are_both_spoken():
    out = _s(
        "temperature-programmed reduction (TPR) was used"
    )
    assert "temperature" in out.lower()
    assert "T P R" in out


def test_definition_only_fires_when_the_initials_match():
    # `(110)` is a facet and `(see Fig. 1)` is an aside: neither is a definition.
    kept = voice_definitions("on the (110) facet")
    assert "(110)" in kept
    out = _s("nuclear magnetic resonance (NMR) was used")
    assert "N M R" in out
    assert "(" not in out


def test_unrelated_parenthesis_is_not_turned_into_an_abbreviation():
    out = voice_definitions("the catalyst (Sigma-Aldrich) was used")
    assert "Sigma-Aldrich" in out


# --- P6/P7: units, ranges and slashes as spoken ------------------------------


def test_units_are_spoken_words():
    assert "molar" in _s("0.1 M").lower()
    assert "minutes" in _s("5 min").lower()
    assert _s("1 h").lower().endswith("hour")
    assert "degrees celsius" in _s("700 \u2103").lower()


def test_range_dash_between_numbers_sharing_a_unit():
    out = _s("cycled from -0.25 V-1.00 V").lower()
    assert " to " in out
    assert "minus 0.25" in out


def test_bare_negative_keeps_its_minus():
    assert "minus" in _s("cooled to -5 \u00b0C").lower()


def test_metal_on_support_and_ratio_slash():
    assert "platinum on carbon" in _s("Pt/C").lower()
    assert "platinum on c n t" in _s("Pt/CNT").lower()
    assert "hydrogen to carbon monoxide" in _s("H2/CO").lower()


def test_unit_over_unit_is_still_per():
    out = _s("750 Wh/L").lower()
    assert "watt hour per liter" in out
    assert "tungsten" not in out


# --- P10: never change a value ------------------------------------------------


def test_orbital_exponent_keeps_its_value():
    out = _s("assigned as t2g5 eg~1.2").lower()
    assert "t two g" in out
    assert "e g" in out
    assert "1.2" in out
    assert " 2 " not in out.replace("1.2", "")


# --- P8: punctuation a speaker can follow ------------------------------------


def test_no_space_before_punctuation():
    out = _s("over Ni, Fe, and Ni-Fe samples showed that")
    assert " ," not in out
    assert " ." not in out


def test_hyphen_joining_a_formula_to_an_acronym_is_not_spoken():
    out = _s("During H2-TPR up to 973 K")
    assert "-" not in out
    assert "T P R" in out


def test_sentence_opens_with_a_capital():
    out = _s("Ni particles were deposited")
    assert out[:1].isupper()


# --- stability ----------------------------------------------------------------


def test_idempotent_on_the_new_cases():
    for raw in (
        "CNTs used in this study",
        "NiO and Fe2O3",
        "Pt/C catalysts",
        "0.1 M HNO3",
        "B-site cations",
        "F-T synthesis",
        "temperature-programmed reduction (TPR)",
    ):
        once = _s(raw)
        assert _s(once) == once, f"{raw} -> {once} -> {_s(once)}"


def test_speak_norm_version_bumped_for_the_new_rules():
    assert SPEAK_NORM_VERSION_DEFAULT == "v7"
    assert load_speak_policy().full_name_abbrev == "say_both"


# --- known remaining, recorded so the next chip has a target ------------------


def test_known_gap_markup_split_formula():
    """`H<sub>2</sub>SO<sub>4</sub>` is not folded into one token yet.

    The plain form is right, so the gap is in sub/sup folding across tags, not in
    the naming rules. design/326 「Not this chip」.
    """
    assert "sulfuric acid" in _s("H2SO4").lower()
    marked = _s("0.1 M H<sub>2</sub>SO<sub>4</sub>").lower()
    assert "sulfuric acid" not in marked  # update when folding is fixed


def test_known_gap_doped_formula_needs_the_paper_term():
    """A fractional doped formula has no good deterministic reading.

    The authors call it BSCF; that has to come from the paper's own dictionary
    (design/326 Phase 2). Until then the legacy expansion stands.
    """
    out = _s("Ba0.5Sr0.5Co0.8Fe0.2O3")
    assert "barium" in out.lower()


# --- found by linting 639 real sentences -------------------------------------


def test_proper_noun_is_not_split_into_elements():
    """`Kröger-Vink` was read as "krypton oger Vink"."""
    for raw, banned in (
        ("Kr\u00f6ger-Vink notation", "krypton"),
        ("Nafion in the film", "sodium"),
        ("Tafel slope", "tantalum"),
        ("Fischer-Tropsch synthesis", "fluorine"),
        ("Barrett-Joyner-Halenda", "barium"),
    ):
        got = _s(raw).lower()
        assert banned not in got, f"{raw} -> {got}"


def test_unit_word_slash_is_per():
    assert "millivolt per decade" in _s("a Tafel slope of 60 mV/decade").lower()
    assert "per min" in _s("a heating rate of 30 K/min").lower()


def test_greater_and_less_than_are_spoken():
    assert "greater than" in _s("stable with &amp;gt; 87% retained").lower()
    assert "less than" in _s("particles &lt;2 nm").lower()


def test_double_escaped_html_is_fully_unescaped():
    out = _s("stable with &amp;gt; 87% retained")
    assert "&" not in out
    assert ">" not in out


def test_spelled_formula_keeps_a_multi_digit_number_whole():
    out = _s("the BZY10 composition")
    assert "B Z Y 10" in out
    assert "1 0" not in out


def test_core_level_notation_keeps_the_symbol():
    out = _s("originating from C 1s and O 1s photoelectrons")
    assert "C one s" in out
    assert "carbon 1s" not in out.lower()


def test_angle_degrees_are_not_celsius():
    out = _s("a step of 0.02\u00b0 and a range from 10 to 80\u00b0").lower()
    assert "degrees" in out
    assert "celsius" not in out
    assert "\u00b0" not in out


def test_celsius_still_says_celsius():
    assert "degrees celsius" in _s("annealing at 1000 \u2103").lower()


def test_helium_is_not_letter_spelled():
    out = _s("10% H2/He was flowing").lower()
    assert "helium" in out
    assert "h e" not in out


def test_ammonium_hydroxide_is_named():
    assert "ammonium hydroxide" in _s("A precipitating agent, NH4OH,").lower()


def test_section_prefix_still_stripped_after_the_proper_noun_guard():
    """`Title:` opens with the titanium symbol, so the guard nearly kept it."""
    out = _s("Title: Nickel catalyst")
    assert not out.lower().startswith("title")
    assert "nickel" in out.lower()


def test_instrument_model_suffix_is_not_elements():
    """`JEM-2200FS` was read as "J E M minus 2200 fluorine sulfur"."""
    out = _s("a JEOL JEM-2200FS microscope")
    assert "fluorine" not in out.lower()
    assert "sulfur" not in out.lower()
    assert "minus" not in out.lower()
    assert "2200" in out


def test_the_model_rule_does_not_eat_formulas():
    """The hyphen is what makes a model label; `CH4` must stay methane."""
    assert "methane" in _s("CH4 oxidation").lower()
    assert "carbon dioxide" in _s("CO2 reduction").lower()
    assert "nickel nitrate" in _s("Ni(NO3)2 solution").lower()
    assert "ammonium hydroxide" in _s("NH4OH was added").lower()


def test_numeric_ratio_slash_is_to():
    out = _s("as diluent, in a 1/60 ratio")
    assert "1 to 60" in out
    assert "/" not in out


def test_paper_terms_win_over_every_builtin_rule():
    """Phase 2 hook: once ingest supplies the term, it is used."""
    out = spoken_text_for_tts(
        "Ba0.5Sr0.5Co0.8Fe0.2O3 catalyzes the OER",
        terms={"Ba0.5Sr0.5Co0.8Fe0.2O3": "B S C F"},
    )
    assert "B S C F" in out
    assert "barium" not in out.lower()
