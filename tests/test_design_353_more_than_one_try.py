"""design/353 — one marker was one chance.

design/352 located 91.6% of box markers. Reading the 31 misses gave four causes, and
three of them spoil only a box's **opening** sentence:

    watermark welded to the front   `BY Cc It has been reported that linear scaling…`
    the tail of the previous column `to free energy and the electronic structure of…`
    an opening longer than the returned sentence (a hyphen, a bullet list)

The box's second and third sentences are untouched by all three, and the previous box's
**closing** sentence names the same boundary from the other side. Adding those took the
corpus from 91.6% to **97.6%**, misses from 31 to 9, and five of ten papers to 100%. The
later openings did the work — 23 rescues against the closing's 1.

Two attempts at this failed first, and both failed the same way: they widened *who gets a
marker* rather than *how many tries a marked box gets*. Letting each sentence qualify on
its own put a marker on every reference-list box, whose entries read like prose line by
line; letting a previous box's closing stand alone admitted apparatus boxes whose
predecessor happened to end in prose. The denominator went from 368 to 664 and then 620,
and `srep41797` fell from 90% to 37% and 42%.
"""

from __future__ import annotations

from sentence_reading.pdf.box_marks import (
    BoxMark,
    assign_boxes,
    box_closing,
    box_openings,
    continues_sentence,
)

BOX = (
    "The catalyst was dried at 120 degrees for twelve hours before the run. "
    "It was then calcined in flowing air at 500 degrees for four hours. "
    "The phase was confirmed by powder diffraction on a sealed tube instrument."
)


def _mark(i: int, box_text: str, *, previous: str = "", start: int = 0) -> BoxMark:
    spans = continues_sentence(previous, box_text)
    return BoxMark(
        index=i,
        start_char=start,
        page=0,
        x0=72.0,
        y0=100.0,
        x1=300.0,
        y1=200.0,
        openings=tuple(box_openings(box_text, continues_previous=spans)),
        closing=box_closing(box_text),
        continues_previous=spans,
    )


# ------------------------------------------------- more than one opening


def test_a_box_offers_its_next_openings_too() -> None:
    openings = box_openings(BOX)
    assert len(openings) == 3
    assert openings[0].startswith("The catalyst was dried")
    assert openings[1].startswith("It was then calcined")


def test_a_watermark_on_the_opening_no_longer_costs_the_box() -> None:
    """`BY Cc` is a licence logo fragment. The returned sentence is the same sentence."""
    box = "BY Cc " + BOX
    marks = [_mark(0, box)]
    sents = [
        "The catalyst was dried at 120 degrees for twelve hours before the run.",
        "It was then calcined in flowing air at 500 degrees for four hours.",
    ]
    owner, census = assign_boxes(marks, sents)
    assert census.to_dict()["marker_missing_n"] == 0
    assert owner[1] == 0


def test_a_later_opening_finds_a_box_whose_first_two_were_dropped() -> None:
    first_box = "Impedance was measured from ten hertz to seven megahertz at each step."
    marks = [
        _mark(0, first_box),
        _mark(1, BOX, previous=first_box, start=len(first_box) + 2),
    ]
    sents = [
        "Impedance was measured from ten hertz to seven megahertz at each step.",
        # Only box 1's third sentence came back.
        "The phase was confirmed by powder diffraction on a sealed tube instrument.",
    ]
    owner, census = assign_boxes(marks, sents)
    assert owner == [0, 1]
    assert census.to_dict()["marker_by_later_n"] == 1


def test_the_closing_marker_is_recorded_but_not_used() -> None:
    """It rescued 1 box of 368 before apparatus boxes were excluded and 0 of 354 after, so
    it is a measured field rather than a branch. This pins that, so the day it is needed
    the number has to change first."""
    marks = [_mark(0, BOX)]
    assert marks[0].closing.startswith("The phase was confirmed")
    _owner, census = assign_boxes(marks, ["Nothing here resembles the box at all."])
    assert census.to_dict()["marker_by_closing_n"] == 0


# ------------------------------------------------- the column break


def test_a_box_continuing_the_previous_sentence_is_named() -> None:
    previous = "The activation enthalpy was obtained from the slope of the fit, which"
    here = "to free energy and the electronic structure of the oxide support."
    assert continues_sentence(previous, here) is True


def test_a_box_starting_its_own_sentence_is_not() -> None:
    previous = "The activation enthalpy was obtained from the slope of the fit."
    assert continues_sentence(previous, BOX) is False


def test_a_continuation_does_not_offer_its_fragment_as_a_boundary() -> None:
    """The sentence belongs to both boxes, so neither can claim it."""
    previous = "The measured conductivity rose steadily with humidity, which points"
    box = "to free energy and the electronic structure of metal oxides. " + BOX
    marks = [_mark(0, box, previous=previous)]
    assert marks[0].continues_previous is True
    assert not marks[0].openings[0].startswith("to free energy")


# ------------------------------------------------- what must not widen


def test_a_reference_list_box_still_gets_nothing() -> None:
    """Its entries read like prose line by line. Letting each sentence qualify on its own
    put a marker on every one of them and halved the measured rate."""
    refs = (
        "(57) Handbook of Binary Alloy Phase Diagrams; ASM International: Materials Park, "
        "OH, 1996. (58) Simonsen, S. B.; Chorkendorff, I.; Dahl, S. Ostwald ripening in a "
        "Pt/SiO2 model catalyst studied by in situ TEM. J. Catal. 2011, 281, 147."
    )
    assert box_openings(refs) == []


def test_an_apparatus_box_is_not_admitted_by_its_predecessor() -> None:
    """A fallback exists for a qualifying box, never as a way in for one that has nothing
    to find. Admitting these took the denominator from 368 to 620."""
    masthead = "SCIENTIFIC REP RTS www.nature.com/scientificreports OPEN received 2015"
    marks = [_mark(0, BOX), _mark(1, masthead, previous=BOX, start=400)]
    _owner, census = assign_boxes(marks, ["The catalyst was dried at 120 degrees for twelve hours before the run."])
    assert census.to_dict()["marker_n"] == 1


def test_the_four_apparatus_shapes_from_the_misses_get_no_marker() -> None:
    """`reference_signal_density` is a density over a region and scores 0.00 on one line,
    so these needed their own signals. All four came from the 31 misses of design/352."""
    for text in (
        "(57) Handbook of Binary Alloy Phase Diagrams; ASM International: "
        "Materials Park, OH, 1996.",
        "Key words: Carbon Nanotubes (CNTs), Pt, Fuel Cell, Electrochemical Deposition.",
        "Funding: This research was funded by the University of New Hampshire start-up fund.",
        "SCIENTIFIC REP RTS Creation of Pd/Al2O3 Catalyst by a Spray Process for Reactors.",
    ):
        assert box_openings(text) == [], text[:50]


def test_real_prose_that_looks_a_little_like_those_still_gets_a_marker() -> None:
    for text in (
        "Three samples were compared: BZY10, BZY20 and the ZnO-added variant of each.",
        "2 wt% Pt was loaded onto the support by incipient wetness impregnation today.",
        "We used DFT and AIMD to model the surface, following the approach of Kreuer.",
        "Figure 5 shows the dependence of conductivity on water vapour pressure here.",
    ):
        assert box_openings(text), text[:50]


def test_the_try_order_puts_the_box_first() -> None:
    """A box's own opening is the boundary. The fallbacks only run when it fails."""
    marks = [_mark(0, BOX)]
    sents = [
        "The catalyst was dried at 120 degrees for twelve hours before the run.",
        "It was then calcined in flowing air at 500 degrees for four hours.",
    ]
    _owner, census = assign_boxes(marks, sents)
    d = census.to_dict()
    assert d["marker_by_first_n"] == 1
    assert d["marker_by_later_n"] == 0
