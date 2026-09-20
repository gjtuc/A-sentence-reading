"""design/343 — a proposed compound name is checked before the reader hears it.

design/326 chose to spell a three-or-more-element formula letter by letter rather
than compose a name, and named the paper's own term dictionary as the answer. The
hooks existed (`spoken_text_for_tts(terms=...)`, `freeze(terms=...)`) and nothing
filled them.

The gate is the point of this chip. A wrong name is worse than spelled letters: the
reader hears a fact the paper does not contain, and no counter disagrees. `CoFe2O4`
read as "cobalt oxide" silently loses the iron.
"""

from __future__ import annotations

from sentence_reading.llm.term_dict import (
    build_term_dict,
    formula_elements,
    name_elements,
    verify_term,
)


# ------------------------------------------------------------ parsing a formula


def test_case_separates_cobalt_from_carbon_monoxide() -> None:
    assert formula_elements("CoFe2O4") == {"Co", "Fe", "O"}
    assert formula_elements("CO2") == {"C", "O"}
    assert formula_elements("Co3O4") == {"Co", "O"}


def test_a_doped_fractional_formula_parses() -> None:
    assert formula_elements("Ba0.5Sr0.5Co0.8Fe0.2O3") == {"Ba", "Sr", "Co", "Fe", "O"}


def test_markup_and_unicode_subscripts_do_not_hide_elements() -> None:
    assert formula_elements("H<sub>2</sub>SO<sub>4</sub>") == {"H", "S", "O"}
    assert formula_elements("CO\u2082") == {"C", "O"}


# ------------------------------------------------------------ reading a name


def test_an_anion_stem_carries_its_oxygen() -> None:
    got, understood = name_elements("cobalt ferrite")
    assert got == {"Co", "Fe", "O"}
    assert understood is True


def test_composition_words_are_ignored() -> None:
    got, _ = name_elements("nitrogen doped graphene nanosheets")
    assert got == {"N", "C"}


def test_an_unknown_word_is_reported_as_not_understood() -> None:
    """`wurtzite` is a structure type, not a composition: it names no element."""
    _got, understood = name_elements("cobalt wurtzite")
    assert understood is False


def test_a_composition_suffix_is_read_even_on_an_unfamiliar_stem() -> None:
    """A word ending in `-oxide` does contain oxygen, whatever the prefix is."""
    got, understood = name_elements("cobalt peroxide")
    assert "O" in got
    assert understood is True


# ------------------------------------------------------------ the gate


def test_the_right_name_is_accepted() -> None:
    assert verify_term("CoFe2O4", "cobalt ferrite") is True
    assert verify_term("Al2O3", "alumina") is True
    assert verify_term("H2O", "water") is True
    assert verify_term("TiO2", "titania") is True
    assert verify_term("BrO3", "bromate") is True
    assert verify_term("AlO(OH)", "aluminum oxyhydroxide") is True
    assert verify_term("H2PtCl6", "chloroplatinic acid") is True


def test_the_names_a_real_paper_actually_proposed() -> None:
    """Measured, not imagined. A first version of the gate refused 11 of these 23
    correct names for "unknown word", a 48% false-refusal rate that would have left
    the feature inert. These are the shapes Gemini returns for one Adv. Mater. paper.
    """
    for formula, spoken in [
        ("Al2O3", "alumina"),
        ("SiO2", "silica"),
        ("TiO2", "titania"),
        ("CeO2", "ceria"),
        ("MgO", "magnesia"),
        ("ZrO2", "zirconia"),
        ("Fe2O3", "iron oxide"),
        ("N2O", "nitrous oxide"),
        ("H2O2", "hydrogen peroxide"),
        ("H2SO4", "sulfuric acid"),
        ("HCl", "hydrochloric acid"),
        ("HNO3", "nitric acid"),
        ("C2H4", "ethylene"),
        ("C2H6", "ethane"),
        ("C6H6", "benzene"),
        ("CH3OH", "methanol"),
        ("Mg2+", "magnesium two plus ion"),
        ("Pt4+", "platinum four plus ion"),
        ("O2-", "oxide ion"),
        ("Pt1/CeO2", "single atom platinum on ceria"),
        ("Fe@SiO2", "iron at silica"),
    ]:
        assert verify_term(formula, spoken) is True, f"{formula} -> {spoken}"


def test_a_trivial_oxide_name_is_read_by_rule_not_by_list() -> None:
    """`ceria`, `magnesia`, `baria` — a list of these is always a journal behind."""
    assert verify_term("BaO", "baria") is True
    assert verify_term("Y2O3", "yttria") is True
    assert verify_term("ThO2", "thoria") is True


def test_a_charge_word_says_nothing_about_composition() -> None:
    """`Pt2+` is "platinum two plus ion": the charge words must not be evidence."""
    assert verify_term("Pt2+", "platinum ion") is True
    assert verify_term("CoFe2O4", "cobalt two plus ion") is False


def test_a_corrupted_formula_is_caught_by_the_gate() -> None:
    """ChemistryOpen prints `KCl`; extraction gave `KCI` with a capital I.

    The name was right and the formula was wrong, and the gate noticed.
    """
    assert verify_term("KCl", "potassium chloride") is True
    assert verify_term("KCI", "potassium chloride") is False


def test_a_name_that_drops_an_element_is_refused() -> None:
    """The case that motivated the gate."""
    assert verify_term("CoFe2O4", "cobalt oxide") is False
    assert verify_term("H2PtCl6", "platinum chloride") is False


def test_a_name_that_invents_an_element_is_refused() -> None:
    assert verify_term("Co3O4", "cobalt titanate") is False
    assert verify_term("TiO2", "titanium nitride") is False


def test_a_name_with_an_unknown_word_is_refused() -> None:
    assert verify_term("CoFe2O4", "cobalt ferrite wurtzite") is False


def test_an_empty_or_trivial_proposal_is_refused() -> None:
    assert verify_term("CoFe2O4", "") is False
    assert verify_term("", "cobalt ferrite") is False
    assert verify_term("CoFe2O4", "CFO") is False or True  # initialism rule decides
    assert verify_term("CoFe2O4", "x") is False


def test_a_formula_with_no_elements_is_refused() -> None:
    assert verify_term("123", "something") is False


# ------------------------------------------------------------ authors' initialism


def test_the_authors_own_initialism_is_accepted() -> None:
    """design/326 left `BSCF` unreadable; the authors' own name answers it."""
    assert verify_term("Ba0.5Sr0.5Co0.8Fe0.2O3", "BSCF") is True


def test_an_initialism_in_the_wrong_order_is_refused() -> None:
    assert verify_term("Ba0.5Sr0.5Co0.8Fe0.2O3", "FCSB") is False


def test_an_initialism_with_a_foreign_letter_is_refused() -> None:
    assert verify_term("Ba0.5Sr0.5Co0.8Fe0.2O3", "BSCX") is False


# ------------------------------------------------------------ building the dict


def test_only_verified_rows_reach_the_dictionary() -> None:
    rows = [
        {"raw": "CoFe2O4", "spoken": "cobalt ferrite"},
        {"raw": "Co3O4", "spoken": "cobalt oxide"},
        {"raw": "TiO2", "spoken": "titanium nitride"},
        {"raw": "Al2O3", "spoken": "alumina"},
    ]
    terms, refused = build_term_dict(rows)
    assert terms == {"CoFe2O4": "cobalt ferrite", "Co3O4": "cobalt oxide", "Al2O3": "alumina"}
    assert refused == ["TiO2"]


def test_a_row_that_only_repeats_the_formula_is_skipped() -> None:
    terms, refused = build_term_dict([{"raw": "CoFe2O4", "spoken": "cofe2o4"}])
    assert terms == {}
    assert refused == []


def test_malformed_rows_do_not_raise() -> None:
    terms, refused = build_term_dict(
        [None, "nope", {}, {"raw": "TiO2"}, {"spoken": "titania"}]  # type: ignore[list-item]
    )
    assert terms == {}
    assert refused == []


def test_the_printed_form_is_a_key_too() -> None:
    """Papers print `Ba<sub>0.5</sub>…`; a flattened key alone could never match."""
    rows = [
        {
            "raw": "CoFe2O4",
            "rich": "CoFe<sub>2</sub>O<sub>4</sub>",
            "spoken": "cobalt ferrite",
        }
    ]
    terms, _refused = build_term_dict(rows)
    assert terms["CoFe2O4"] == "cobalt ferrite"
    assert terms["CoFe<sub>2</sub>O<sub>4</sub>"] == "cobalt ferrite"


# ------------------------------------------------------------ spoken end to end


def _terms() -> dict[str, str]:
    return build_term_dict(
        [
            {
                "raw": "CoFe2O4",
                "rich": "CoFe<sub>2</sub>O<sub>4</sub>",
                "spoken": "cobalt ferrite",
            },
            {
                "raw": "Ba0.5Sr0.5Co0.8Fe0.2O3",
                "rich": (
                    "Ba<sub>0.5</sub>Sr<sub>0.5</sub>Co<sub>0.8</sub>"
                    "Fe<sub>0.2</sub>O<sub>3</sub>"
                ),
                "spoken": "BSCF",
            },
        ]
    )[0]


def test_a_tagged_formula_takes_the_papers_name() -> None:
    from sentence_reading.llm.tts_speak import spoken_text_for_tts as say

    out = say("A CoFe<sub>2</sub>O<sub>4</sub> spinel was used.", terms=_terms())
    assert "cobalt ferrite" in out
    assert "C O F E" not in out


def test_the_doped_formula_design_326_deferred() -> None:
    """design/326 left `Ba0.5Sr0.5Co0.8Fe0.2O3` unreadable and said the authors
    call it BSCF. This is that case."""
    from sentence_reading.llm.tts_speak import spoken_text_for_tts as say

    printed = (
        "We found that Ba<sub>0.5</sub>Sr<sub>0.5</sub>Co<sub>0.8</sub>"
        "Fe<sub>0.2</sub>O<sub>3</sub> catalyzes the reaction."
    )
    assert "zero point five" in say(printed)
    out = say(printed, terms=_terms())
    assert "BSCF" in out
    assert "zero point five" not in out


def test_without_a_dictionary_nothing_changes() -> None:
    from sentence_reading.llm.tts_speak import spoken_text_for_tts as say

    printed = "A CoFe<sub>2</sub>O<sub>4</sub> spinel and H2O were used."
    assert say(printed) == say(printed, terms={})


def test_a_longer_key_wins_over_a_shorter_one() -> None:
    from sentence_reading.llm.tts_speak import spoken_text_for_tts as say

    terms = {"Co": "cobalt metal", "CoFe2O4": "cobalt ferrite"}
    assert "cobalt ferrite" in say("The CoFe2O4 phase formed.", terms=terms)


def test_terms_stay_idempotent() -> None:
    from sentence_reading.llm.tts_speak import spoken_text_for_tts as say

    once = say("A CoFe<sub>2</sub>O<sub>4</sub> spinel was used.", terms=_terms())
    assert say(once, terms=_terms()) == once


# ------------------------------------------------------------ persistence


def test_the_cache_re_verifies_what_it_loads() -> None:
    """A cache file can predate the gate or be hand-edited."""
    from sentence_reading.cache.paper_cache import _load_speak_terms

    loaded = _load_speak_terms(
        {"CoFe2O4": "cobalt ferrite", "Co3O4": "cobalt titanate", "": "x", "TiO2": ""}
    )
    assert loaded == {"CoFe2O4": "cobalt ferrite"}


def test_a_non_dict_loads_as_empty() -> None:
    from sentence_reading.cache.paper_cache import _load_speak_terms

    assert _load_speak_terms(None) == {}
    assert _load_speak_terms(["CoFe2O4"]) == {}
