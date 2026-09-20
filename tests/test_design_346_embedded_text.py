"""design/346 — the service's boxes, the paper's letters.

design/345 found that the layout service's *reading* of a page changes between calls:
one run of an Elsevier paper replaced every `o` with a two-character sequence 1,483
times, the next run of the same file was clean, and an RSC review came back with `y`
as `γ` 440 times. The PDF's embedded text does not vary and was right every time.

The boxes carry page coordinates in PDF points, so the paper's own words inside a box
can be asked for directly — no similarity matching. Where the two readings disagreed,
the PDF was correct in every case:

    service  BaZro.9    6gb      Ap(0)    PH20     "total
    PDF      BaZr0.9    sigma-gb dphi(0)  pH2O     sigma-total

Measured over four papers, 700 paragraphs of 80 characters or more: the service's
words are present in the clip with median agreement 1.0000, the clip carries no
foreign words (median 1.0000 back), word *order* similarity is 1.0000 with none
broken, and 5 paragraphs fall below 0.80 — all five identified in the tests below.
"""

from __future__ import annotations

from sentence_reading.pdf.embedded_text import (
    MAX_WORD_LETTERS,
    MIN_AGREEMENT,
    MIN_CHARS_TO_REPLACE,
    agreement,
    prefer_embedded,
    runs_together,
    text_in_box,
)

# (x0, y0, x1, y1, text)
PARAGRAPH = [
    (72.0, 100.0, 120.0, 110.0, "Protonic"),
    (124.0, 100.0, 150.0, 110.0, "and"),
    (154.0, 100.0, 200.0, 110.0, "electronic"),
    (72.0, 112.0, 120.0, 122.0, "hole"),
    (124.0, 112.0, 200.0, 122.0, "conductivity"),
]
NEIGHBOUR = [
    (72.0, 126.0, 200.0, 136.0, "Introduction"),
    (300.0, 100.0, 380.0, 110.0, "othercolumn"),
]

LONG = (
    "Protonic and electronic hole conductivity of grain interior and grain boundaries "
    "was measured by impedance spectroscopy over a wide range of oxygen pressure."
)


# ------------------------------------------------- taking the words out of a box


def test_only_the_words_inside_the_box() -> None:
    got = text_in_box(PARAGRAPH + NEIGHBOUR, 72.0, 100.0, 200.0, 122.0)
    assert got == "Protonic and electronic hole conductivity"


def test_a_line_just_outside_does_not_arrive() -> None:
    """The reason for centre containment: a clip that keeps touching lines whole
    pulled in as many foreign words as the paragraph had, on 64 of 91 paragraphs."""
    got = text_in_box(PARAGRAPH + NEIGHBOUR, 72.0, 100.0, 200.0, 122.0)
    assert "Introduction" not in got
    assert "othercolumn" not in got


def test_an_empty_region_yields_nothing() -> None:
    assert text_in_box(PARAGRAPH, 400.0, 400.0, 500.0, 450.0) == ""


# ------------------------------------------------- choosing which reading to use


def test_the_paper_wins_when_the_readings_agree() -> None:
    """The service misread `BaZr0.9` as `BaZro.9`; the PDF has it right."""
    service = LONG.replace("Protonic", "Prot0nic")
    text, why = prefer_embedded(service, LONG)
    assert why == "replaced"
    assert text == LONG


def test_the_elsevier_corruption_is_replaced() -> None:
    service = LONG.replace("o", "?<sub>h</sub>")
    text, why = prefer_embedded(service, LONG)
    assert why == "replaced"
    assert "<sub>h</sub>" not in text


def test_no_embedded_text_keeps_the_service_reading() -> None:
    """Labels drawn inside a figure, and scanned pages. 3 of 700."""
    text, why = prefer_embedded(LONG, "")
    assert (text, why) == (LONG, "kept_no_embedded")


def test_a_short_box_keeps_the_service_reading() -> None:
    """The PDF renders `ABSTRACT` letter-spaced, which would break heading
    recognition, and axis ticks are drawn inside the figure image."""
    text, why = prefer_embedded("ABSTRACT", "A B S T R A C T")
    assert (text, why) == ("ABSTRACT", "kept_short")
    assert len("ABSTRACT") < MIN_CHARS_TO_REPLACE


SERVICE_RUN = (
    "semiconductor can be obtained, as depicted in Fig. 8B. The transferred charge "
    "is half of the amount of the donor concentration in the depletion layer."
)
PDF_RUN = (
    "semiconductor can be obtained, as depicted in Fig. 8B. The "
    "transferredchargeishalfoftheamountofthedonorconcentration"
)


def test_a_font_without_spaces_is_refused() -> None:
    """An RSC paragraph whose embedded font has no space glyphs. Substituting it would
    be worse than the corruption this repair exists to fix."""
    assert runs_together(SERVICE_RUN, PDF_RUN) is True
    text, why = prefer_embedded(SERVICE_RUN, PDF_RUN)
    assert (text, why) == (SERVICE_RUN, "kept_runs_together")


def test_a_genuinely_long_word_is_not_mistaken_for_it() -> None:
    """`hydrodechlorination` is 19 letters and is the longest legitimate word of 697
    clips. The test is relative to the service's own reading of the same box."""
    both = "Liquid phase catalytic hydrodechlorination of the azo dye was measured here."
    assert runs_together(both, both) is False
    _text, why = prefer_embedded(both + " " + both, both + " " + both)
    assert why == "replaced"


def test_severe_corruption_still_gets_repaired() -> None:
    """The guard that catches the run-together font must not also block this. When
    every `o` is replaced the two readings agree almost nowhere, so agreement alone
    would refuse the repair exactly where it is needed."""
    service = LONG.replace("o", "?<sub>h</sub>")
    assert agreement(service, LONG) < MIN_AGREEMENT
    text, why = prefer_embedded(service, LONG)
    assert (text, why) == (LONG, "replaced")


def test_an_unexplained_mismatch_is_still_refused() -> None:
    """A sound-looking reading that disagrees with the clip means something else is
    wrong — wrong page, rotated page — and the clip is not trusted."""
    other = (
        "Water content was measured with Karl Fisher titration using a cell coupled to "
        "a vaporiser unit held at two hundred degrees for the duration of the run."
    )
    text, why = prefer_embedded(LONG, other)
    assert (text, why) == (LONG, "kept_disagree")


def test_agreement_ignores_case_and_punctuation() -> None:
    assert agreement("Fig. 5 shows the bulk", "fig 5 shows the bulk!") == 1.0


def test_agreement_of_empty_service_text_is_total() -> None:
    assert agreement("", "anything at all") == 1.0


def test_the_word_length_bound_sits_between_the_measured_cases() -> None:
    """19 letters is the longest legitimate word of 697 clips; 24 is the broken one."""
    assert 19 <= MAX_WORD_LETTERS < 24
