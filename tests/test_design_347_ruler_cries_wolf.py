"""design/347 — the ruler was wrong more often than the pipeline.

design/344 reported that ten papers each lost 3 to 24 real sentences, and design/345
built a per-chunk floor on that reading before withdrawing it. Opening one case by
hand ended the story:

    source  ... covered with BZY10-1 wt% BaCO3 sacrifi- cial powder for sintering.
    output  ... covered with BaZr<sub>0.9</sub>Y<sub>0.1</sub>O<sub>3-d</sub>-1 wt% ...

The sentence was there. The model had expanded the abbreviation into the full formula,
which is exactly what the system prompt asks for: *prefer glossary rich forms from
PAPER CONTEXT when the same raw token appears*. Five-word shingles cannot survive our
own instruction.

A load test had already pointed the same way. The failing chunk was run twelve times
across four conditions — full prompt and a slimmed one, whole chunk and split in
halves — and returned **exactly 22 sentences every time**, while the ruler's score
moved between 0.730 and 1.000. A constant count with a moving score is a ruler
problem, not a capacity problem.

Re-reading the stored traces, the shingle ruler alone was wrong about **18 of 33**
fragments. With word overlap as a second look, and author biographies excluded, 15 of
those 33 resolve and what remains is 13 partial deliveries and **2 real losses** — two
body sentences of an 805-sentence review.
"""

from __future__ import annotations

from sentence_reading.llm.debone_quality import (
    TEXT_REWORDED_SHARE,
    text_coverage,
)
from sentence_reading.models import Sentence

SOURCE_SENTENCE = (
    "After being heated at 600 C for 2 h to remove the binder, the pellets were "
    "covered with BZY10-1 wt% BaCO3 sacrificial powder for sintering."
)
# What came back: the abbreviation expanded per the prompt's glossary instruction.
EXPANDED = (
    "After being heated at 600 C for 2 h to remove the binder, the pellets were "
    "covered with BaZr<sub>0.9</sub>Y<sub>0.1</sub>O<sub>3-&delta;</sub>-1 wt% "
    "BaCO<sub>3</sub> sacrificial powder for sintering."
)
OTHER = (
    "Water content was measured with Karl Fisher titration using a cell coupled to a "
    "vaporiser unit, and the impedance spectra were analysed with circuit software."
)


def _sents(*texts: str) -> list[Sentence]:
    return [Sentence(id=str(i), text=t, section="experimental") for i, t in enumerate(texts)]


# ------------------------------------------------- the case that ended the story


def test_an_expanded_abbreviation_is_not_a_loss() -> None:
    ratio, missing = text_coverage(SOURCE_SENTENCE + " " + OTHER, _sents(EXPANDED, OTHER))
    assert missing == []
    assert ratio == 1.0


def test_restored_typography_is_not_a_loss() -> None:
    src = "The conductivity of H2O saturated samples rose above 600 C in wet air today."
    out = "The conductivity of H<sub>2</sub>O saturated samples rose above 600 C in wet air today."
    _ratio, missing = text_coverage(src, _sents(out))
    assert missing == []


# ------------------------------------------------- what must still be reported


def test_a_sentence_that_is_really_gone_is_still_named() -> None:
    """Two body sentences of the RSC review were genuinely absent. Those must survive
    the second look, or the ruler becomes useless in the other direction."""
    gone = (
        "Aside from the context of metal support interaction, the term reducibility is "
        "also frequently encountered in oxygen mediated catalytic reaction studies."
    )
    ratio, missing = text_coverage(gone + " " + OTHER, _sents(OTHER))
    assert len(missing) == 1
    assert "reducibility" in missing[0]
    assert ratio < 1.0


def test_a_paraphrase_that_shares_few_words_is_still_a_loss() -> None:
    src = (
        "The pellets were sintered at 1650 degrees for ten hours in a covered alumina "
        "crucible to limit barium evaporation during the treatment."
    )
    unrelated = (
        "Impedance spectroscopy was performed between ten hertz and seven megahertz "
        "using a frequency response analyser at each temperature step."
    )
    _ratio, missing = text_coverage(src + " " + OTHER, _sents(unrelated, OTHER))
    assert len(missing) == 1


def test_the_overlap_bar_is_high_enough_to_mean_something() -> None:
    """At 0.70 a fragment has to share most of its words with one returned sentence,
    not merely share a topic with it."""
    assert 0.6 < TEXT_REWORDED_SHARE <= 0.8


# ------------------------------------------------- author biographies


def test_an_author_biography_is_not_reported_as_lost_prose() -> None:
    """Dropping these is correct. Reporting them as loss buried the real finding: all
    five fragments the first pass called absent were of this kind."""
    for bio in (
        "Denis Leybo received his PhD from the National University of Science and "
        "Technology MISIS, Russia, and works on inorganic nanomaterials there.",
        "Matteo Monai has been Assistant Professor at Utrecht University since 2021 "
        "and studies metal support interaction in working catalysts.",
        "In 2020 he joined the Inorganic Nanomaterials laboratory at NUST MISIS, "
        "where he worked on the synthesis of boron nitride nanostructures.",
        "Her research interests include operando spectroscopy of supported metal "
        "catalysts and the design of selective hydrogenation systems.",
    ):
        _ratio, missing = text_coverage(bio + " " + OTHER, _sents(OTHER))
        assert missing == [], bio[:60]


def test_naming_a_person_in_results_is_not_a_biography() -> None:
    """The verb phrase is required, so a results sentence crediting someone stays."""
    src = (
        "The same trend was reported by Kreuer and co-workers, who measured a similar "
        "activation enthalpy for proton transport in acceptor doped barium zirconate."
    )
    _ratio, missing = text_coverage(src + " " + OTHER, _sents(OTHER))
    assert len(missing) == 1
