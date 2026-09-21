"""design/352 — keep the coordinates instead of searching for them later.

The layout service hands back each paragraph as a box with a page and coordinates, and
those coordinates are what put the paper in reading order. Then they are discarded, so
anything downstream that wants a sentence's position has to search the whole paper for
six of its words — which is how design/351's order check found a passage 47,000
characters away that merely read alike, and reported 44% on a paper whose order is 99%
right.

A box's **first sentence**, remembered before the text goes anywhere, is enough to find
the box again. Measured over ten papers and 357 prose boxes: 91.9% of markers are found,
305 of them to within 5%.

Two faults had to be fixed to get there, and both are tested below: sentence ends hidden
by a citation set against the full stop, and comparing words where the difference is a
letter.
"""

from __future__ import annotations

from sentence_reading.pdf.box_marks import (
    MARK_MATCH_MIN,
    MARK_MATCH_SURE,
    BoxMark,
    assign_boxes,
    first_sentence,
    match_score,
    split_sentences_for_marks,
)


def _mark(i: int, start: int, marker: str) -> BoxMark:
    return BoxMark(
        index=i, start_char=start, page=0, x0=72.0, y0=100.0, x1=300.0, y1=200.0, marker=marker
    )


# ------------------------------------------------- sentence ends hidden by a citation


def test_a_bracket_citation_does_not_hide_the_sentence_end() -> None:
    """Wiley: `catalysis.[3] Because …`. Splitting on full-stop-then-space glued three
    sentences into one marker, and no returned sentence could match it."""
    text = (
        "Single-atom catalysts bridge the gap between homogeneous and heterogeneous "
        "catalysis.[3] Because of their high atom efficiency they are attractive. "
        "Different terms have been used to describe these catalysts.[7]"
    )
    parts = split_sentences_for_marks(text)
    assert len(parts) == 3
    assert parts[0].endswith("catalysis.")
    assert parts[1].startswith("Because of their high atom")


def test_a_superscript_citation_does_not_hide_it_either() -> None:
    """RSC: the superscript extracts as bare digits welded to the stop."""
    text = (
        "They reported the reductive exsolution of metallic elements at high "
        "temperature.175 The application of this idea is broad."
    )
    parts = split_sentences_for_marks(text)
    assert len(parts) == 2
    assert parts[0].endswith("temperature.")


def test_a_list_of_superscript_citations_too() -> None:
    """`recognized.50,51 The term …` — the variant still missing at 91%."""
    text = (
        "The possibility of supports modifying metal particles has long been "
        "recognized.50,51 The term reducibility is also used loosely."
    )
    parts = split_sentences_for_marks(text)
    assert len(parts) == 2
    assert parts[0].endswith("recognized.")


def test_a_decimal_is_not_mistaken_for_a_citation() -> None:
    """`0.15 was` and `Fig. 3b shows` must not be cut, so the rule wants a capital or an
    opening bracket after the number."""
    text = "The ratio reached 0.15 in wet air. Fig. 3b shows the same trend clearly."
    parts = split_sentences_for_marks(text)
    assert len(parts) == 2
    assert "0.15" in parts[0]


# ------------------------------------------------- comparing letters, not words


def test_a_line_break_hyphen_is_not_a_different_sentence() -> None:
    """`size depen- dence` is three tokens against one, and two characters in ninety."""
    marker = "Ioannides and Verykios considered the metal donor- doped TiO2 system to deduce size depen- dence"
    got = "Ioannides and Verykios considered the metal donor-doped TiO2 system to deduce size dependence"
    assert match_score(marker, got) >= MARK_MATCH_SURE


def test_a_misread_glyph_is_not_a_different_sentence() -> None:
    """design/345's corruption: one letter in a hundred and fifty."""
    marker = "Fu and Wagner postulated that the work function of the AM, jM, and the formation enthalpy differ"
    got = "Fu and Wagner postulated that the work function of the AM, \u03c6M, and the formation enthalpy differ"
    assert match_score(marker, got) >= MARK_MATCH_SURE


def test_an_expanded_abbreviation_still_scores(  ) -> None:
    """design/347: the prompt asks for the glossary's rich form."""
    marker = "The pellets were covered with BZY10 sacrificial powder before sintering began"
    got = (
        "The pellets were covered with BaZr<sub>0.9</sub>Y<sub>0.1</sub>O<sub>3</sub> "
        "sacrificial powder before sintering began"
    )
    assert match_score(marker, got) >= MARK_MATCH_MIN


def test_a_different_sentence_does_not_match() -> None:
    marker = "The catalyst was dried at 120 degrees for twelve hours before the run"
    other = "Impedance spectroscopy was performed between ten hertz and seven megahertz"
    assert match_score(marker, other) < MARK_MATCH_MIN


def test_a_sentence_that_merely_contains_the_marker_later_scores_lower() -> None:
    """Prefix-anchored: a marker is a box's *first* sentence."""
    marker = "The surface energy of the oxide support governs encapsulation strongly"
    buried = (
        "As noted in the preceding paragraph and in several earlier reviews of this "
        "subject, the surface energy of the oxide support governs encapsulation strongly"
    )
    assert match_score(marker, buried) < MARK_MATCH_SURE


# ------------------------------------------------- picking the marker


def test_a_heading_is_not_a_usable_marker() -> None:
    assert first_sentence("3.2.5. Raman Spectroscopy") == ""
    assert first_sentence("") == ""


def test_the_marker_is_the_boxs_opening_sentence() -> None:
    box = (
        "Many approaches have been developed to prepare these catalysts.[12] Wet "
        "chemistry is the most common of them."
    )
    assert first_sentence(box).endswith("catalysts.")


# ------------------------------------------------- assigning sentences to boxes


def test_sentences_take_the_box_of_the_marker_above_them() -> None:
    marks = [
        _mark(0, 0, "Single-atom catalysts bridge the gap between two fields of study"),
        _mark(1, 400, "Many approaches have been developed to prepare these catalysts"),
    ]
    sents = [
        "Single-atom catalysts bridge the gap between two fields of study.",
        "Because of their high atom efficiency they are attractive for industry.",
        "Different terms have been used to describe them in the literature.",
        "Many approaches have been developed to prepare these catalysts.",
        "Wet chemistry is the most common of them by a wide margin.",
    ]
    owner, census = assign_boxes(marks, sents)
    assert owner == [0, 0, 0, 1, 1]
    assert census.found_sure == 2
    assert census.not_found == 0


def test_a_missing_marker_costs_precision_not_correctness() -> None:
    """Its sentences fall to the box before it, which is its neighbour in reading order."""
    marks = [
        _mark(0, 0, "Single-atom catalysts bridge the gap between two fields of study"),
        _mark(1, 400, "This opening sentence was dropped and never came back at all"),
        _mark(2, 800, "Many approaches have been developed to prepare these catalysts"),
    ]
    sents = [
        "Single-atom catalysts bridge the gap between two fields of study.",
        "A sentence from the middle box whose opening never returned.",
        "Many approaches have been developed to prepare these catalysts.",
    ]
    owner, census = assign_boxes(marks, sents)
    assert census.not_found == 1
    assert owner == [0, 0, 2]
    assert all(o >= 0 for o in owner)


def test_a_repeated_phrase_cannot_pull_a_box_backwards() -> None:
    """Each search starts after the last marker found, so the abstract's echo of a
    conclusion sentence cannot claim the conclusion's box."""
    marks = [
        _mark(0, 0, "The catalyst retained its activity for forty hours on stream"),
        _mark(1, 900, "The catalyst retained its activity for forty hours on stream"),
    ]
    sents = [
        "The catalyst retained its activity for forty hours on stream.",
        "A middle sentence that belongs to the first box only.",
        "The catalyst retained its activity for forty hours on stream.",
    ]
    owner, _census = assign_boxes(marks, sents)
    assert owner == [0, 0, 1]


def test_sentences_before_the_first_marker_are_left_unassigned() -> None:
    marks = [_mark(0, 500, "Many approaches have been developed to prepare these catalysts")]
    sents = [
        "A front matter line that precedes every box.",
        "Many approaches have been developed to prepare these catalysts.",
    ]
    owner, _census = assign_boxes(marks, sents)
    assert owner == [-1, 0]


def test_the_census_reports_what_happened() -> None:
    marks = [_mark(0, 0, "Single-atom catalysts bridge the gap between two fields")]
    owner, census = assign_boxes(marks, ["Nothing resembling the marker at all here."])
    d = census.to_dict()
    assert d["box_n"] == 1
    assert d["marker_n"] == 1
    assert d["marker_missing_n"] == 1
    assert owner == [-1]


def test_no_marks_is_not_an_error() -> None:
    owner, census = assign_boxes([], ["One sentence."])
    assert owner == [-1]
    assert census.to_dict()["box_n"] == 0


# ------------------------------------------------- the starvation that cost 62 points
#
# Both tests below guard one fault seen twice: a marginal match far ahead moves the
# forward cursor and every box behind it is starved. On `srep41797` a masthead box
# scraped past the floor at 0.72 against sentence 166 of 192, moved the cursor from 45 to
# 167, and the seventeen real boxes that followed found nothing — 90% of markers down to
# 28%. Across the corpus the two fixes took 67.4% to 91.6%.


def test_an_apparatus_box_gets_no_marker() -> None:
    """It has nothing to find among practice sentences, so letting it search is the fault."""
    for apparatus in (
        "Scientific Reports www.nature.com/scientificreports OPEN ARTICLE received",
        "Allen,\u2020 Sungwoo Lee,\u2020 Heeyeon Kim,\u2020 Euijoon Yoon,\u2020 Haimei Zheng,\u2020 Angus I.",
        "Denis Leybo received his PhD from the National University of Science and Technology.",
        "H2 produced (\u00b5mol .min-1) CO produced (\u00b5mol .min-1) conversion of methane",
    ):
        assert first_sentence(apparatus) == "", apparatus[:50]


def test_a_prose_box_still_gets_one() -> None:
    prose = (
        "The catalyst was dried at 120 degrees for twelve hours before the run. "
        "It was then calcined in flowing air."
    )
    assert first_sentence(prose).startswith("The catalyst was dried")


def test_a_marginal_match_far_ahead_does_not_starve_the_boxes_behind_it() -> None:
    """The earliest credible match wins, not the highest-scoring one further along."""
    marks = [
        _mark(0, 0, "The catalyst was dried at 120 degrees for twelve hours before the run"),
        _mark(1, 900, "Impedance spectroscopy was performed from ten hertz to seven megahertz"),
        _mark(2, 1800, "Water content was measured with Karl Fisher titration in a cell"),
    ]
    sents = [
        "The catalyst was dried at 120 degrees for twelve hours before the run.",
        "It was then calcined in flowing air at 500 degrees for four hours.",
        "Impedance spectroscopy was performed from ten hertz to seven megahertz.",
        "The spectra were analysed with equivalent circuit software throughout.",
        "Water content was measured with Karl Fisher titration in a cell.",
        # A late near-repeat of box 0's opening, which must not pull the cursor forward.
        "The catalyst was dried at 120 degrees for twelve hours before each run.",
    ]
    owner, census = assign_boxes(marks, sents)
    assert census.to_dict()["marker_missing_n"] == 0
    assert owner == [0, 0, 1, 1, 2, 2]
