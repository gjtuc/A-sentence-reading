"""design/354 — a box found by its second sentence starts before that sentence.

design/353 let a box try its second and third openings, which found 19 boxes that would
otherwise have been lost. It left a gap. `assign_boxes` gives a box every sentence from
the one its marker matched, so when the *second* opening is what won, the box's first
sentence — if the model did return it, and simply was not the marker that matched — stays
credited to the **previous** box.

The previous box's **closing** sentence settles it: matched at output j, the next box
starts at j+1.

design/353 had built that field and measured it for a different job — as a way to *find* a
box whose own openings all failed — scored 0 of 354, and left it unused. Measured for the
job it was proposed for, it matched in **17 of the 18** cases where a later opening won and
moved **16 sentences** to the box that produced them: 9 and 5 in the RSC review, 2 in
`srep41797`.

That is 0.7% of the corpus's sentences, and it is a wrong box rather than an imprecise one.
"""

from __future__ import annotations

from sentence_reading.pdf.box_marks import (
    BoxMark,
    assign_boxes,
    box_closing,
    box_openings,
    continues_sentence,
)

BOX_A = (
    "Impedance was measured from ten hertz to seven megahertz at each step. "
    "The spectra were fitted with an equivalent circuit for every temperature."
)
BOX_B = (
    "The catalyst was dried at 120 degrees for twelve hours before the run. "
    "It was then calcined in flowing air at 500 degrees for four hours. "
    "The phase was confirmed by powder diffraction on a sealed tube instrument."
)


def _mark(i: int, text: str, *, previous: str = "", start: int = 0) -> BoxMark:
    spans = continues_sentence(previous, text)
    return BoxMark(
        index=i,
        start_char=start,
        page=0,
        x0=72.0,
        y0=100.0,
        x1=300.0,
        y1=200.0,
        openings=tuple(box_openings(text, continues_previous=spans)),
        closing=box_closing(text),
        continues_previous=spans,
    )


def test_a_first_sentence_that_came_back_is_not_left_with_the_previous_box() -> None:
    """The gap design/353 left. Box B's opening is returned but reworded past matching, so
    its second opening wins — and without the correction its first sentence goes to A."""
    marks = [_mark(0, BOX_A), _mark(1, BOX_B, previous=BOX_A, start=200)]
    sents = [
        "Impedance was measured from ten hertz to seven megahertz at each step.",
        "The spectra were fitted with an equivalent circuit for every temperature.",
        # Box B's opening, rewritten enough that it is not the marker that wins.
        "Prior to the run the catalyst underwent drying at 120 degrees for half a day.",
        "It was then calcined in flowing air at 500 degrees for four hours.",
    ]
    owner, census = assign_boxes(marks, sents)
    assert census.to_dict()["marker_by_later_n"] == 1
    assert census.to_dict()["marker_boundary_fixed_n"] == 1
    assert owner == [0, 0, 1, 1]


def test_no_correction_when_the_boundary_was_already_right() -> None:
    """The previous box's closing matching immediately before the win means nothing
    slipped. On `srep41797` that was true of a 48-sentence gap."""
    marks = [_mark(0, BOX_A), _mark(1, BOX_B, previous=BOX_A, start=200)]
    sents = [
        "Impedance was measured from ten hertz to seven megahertz at each step.",
        "The spectra were fitted with an equivalent circuit for every temperature.",
        "It was then calcined in flowing air at 500 degrees for four hours.",
    ]
    owner, census = assign_boxes(marks, sents)
    assert census.to_dict()["marker_boundary_fixed_n"] == 0
    assert owner == [0, 0, 1]


def test_the_first_opening_winning_needs_no_correction() -> None:
    marks = [_mark(0, BOX_A), _mark(1, BOX_B, previous=BOX_A, start=200)]
    sents = [
        "Impedance was measured from ten hertz to seven megahertz at each step.",
        "The catalyst was dried at 120 degrees for twelve hours before the run.",
    ]
    _owner, census = assign_boxes(marks, sents)
    d = census.to_dict()
    assert d["marker_by_first_n"] == 2
    assert d["marker_boundary_fixed_n"] == 0


def test_a_missing_closing_leaves_the_boundary_where_it_was() -> None:
    """Without the other side there is no evidence to move it, so it is not moved."""
    a = _mark(0, BOX_A)
    marks = [
        BoxMark(
            index=0,
            start_char=0,
            page=0,
            x0=0.0,
            y0=0.0,
            x1=0.0,
            y1=0.0,
            openings=a.openings,
            closing="",
        ),
        _mark(1, BOX_B, previous=BOX_A, start=200),
    ]
    sents = [
        "Impedance was measured from ten hertz to seven megahertz at each step.",
        "Prior to the run the catalyst underwent drying at 120 degrees for half a day.",
        "It was then calcined in flowing air at 500 degrees for four hours.",
    ]
    owner, census = assign_boxes(marks, sents)
    assert census.to_dict()["marker_boundary_fixed_n"] == 0
    assert owner[1] == 0


def test_a_correction_never_runs_past_the_previous_boxs_own_sentences() -> None:
    """The closing names the previous box's last sentence, so the boundary can only move
    back as far as just after it — never into the previous box."""
    marks = [_mark(0, BOX_A), _mark(1, BOX_B, previous=BOX_A, start=200)]
    sents = [
        "Impedance was measured from ten hertz to seven megahertz at each step.",
        "The spectra were fitted with an equivalent circuit for every temperature.",
        "Prior to the run the catalyst underwent drying at 120 degrees for half a day.",
        "It was then calcined in flowing air at 500 degrees for four hours.",
    ]
    owner, _census = assign_boxes(marks, sents)
    # Box A keeps both of its own sentences.
    assert owner[0] == 0 and owner[1] == 0
