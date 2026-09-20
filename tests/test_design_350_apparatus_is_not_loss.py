"""design/350 — an accurate missing report, so the next real finding is visible.

Once design/349 removed the genuine losses, everything still listed as missing was
apparatus the pipeline drops on purpose. Reporting it as lost prose is how design/344's
real finding got buried in the first place: 5 of its named losses were author
biographies and nobody looked past them.

Every shape below is a fragment taken from the ten-paper corpus, and every `REAL`
sentence below must keep being reported — a filter that hides a real loss is worse than
no filter.
"""

from __future__ import annotations

from sentence_reading.llm.debone_quality import (
    _worth_reporting_missing,
    is_front_or_reference_apparatus,
)

APPARATUS = {
    "author biography (RSC review)": "Denis Leybo received his PhD from the National "
    "University of Science and Technology MISIS, Russia, and works there still.",
    "biography, other phrasing": "Her research is aimed at gaining fundamental insights "
    "in catalysts at work to improve or create new catalytic processes.",
    "biography, a named group": "In 2023, he joined Charlotte Vogt\u2019s group at the "
    "Technion, the Israel Institute of Technology, to study operando spectroscopy.",
    "author list with daggers": "Allen,\u2020 Sungwoo Lee,\u2020 Heeyeon Kim,\u2020 "
    "Euijoon Yoon,\u2020 Haimei Zheng,\u2020 Angus I.",
    "affiliation block": "Warner*,\u2020 \u2021Department of Materials, University of "
    "Oxford, Parks Road, Oxford, OX1 3PH, United Kingdom",
    "series citation": "367 of Astronomical Society of the Pacific Conference Series "
    "(Astronomical Society of the Pacific, 2007), p.",
    "supplementary file list": "Formation of the 855 line defect (AVI) Motion of kink "
    "through two SW type bond rotations in graphene (AVI) CVD growth of layers (AVI)",
    "figure axis labels": "( FCH4in \u2212 FCH4out FCH4in ) H2 produced "
    "(\u00b5mol .min-1) CO produced (\u00b5mol .min-1) layer besides the removal",
}

REAL = {
    "methods, cata13": "The procedure is the same as the H2-TPR experiment described "
    "previously for the calcinated catalysts.",
    "body, d4cs": "However, the aspect ratio or shape can change significantly for "
    "similar particle sizes depending on the support used.",
    "body, d4cs 2": "Aside from the context of metal support interaction, the term "
    "reducibility is also frequently encountered in oxygen mediated reaction studies.",
    "methods, plain": "The catalyst was dried at 120 degrees for twelve hours and then "
    "calcined in flowing air at 500 degrees for four hours.",
    "results with a unit": "The conductivity reached 3.2 mS per centimetre at 600 "
    "degrees in wet air, which is close to the reported value for this composition.",
    "results crediting a person": "The same trend was reported by Kreuer and "
    "co-workers, who measured a similar activation enthalpy for proton transport.",
}


def test_apparatus_is_not_reported_as_lost_prose() -> None:
    for name, text in APPARATUS.items():
        assert is_front_or_reference_apparatus(text) is True, name
        assert _worth_reporting_missing(text) is False, name


def test_real_prose_is_still_reported() -> None:
    for name, text in REAL.items():
        assert is_front_or_reference_apparatus(text) is False, name
        assert _worth_reporting_missing(text) is True, name


def test_one_dagger_is_not_an_author_block() -> None:
    """A footnote marker appears in body text too. Three is a list of authors."""
    one = (
        "The sample labelled BZY10\u2020 was sintered for ten hours, and its grain size "
        "was measured from the fracture surface."
    )
    assert is_front_or_reference_apparatus(one) is False


def test_one_unit_in_parentheses_is_not_an_axis_label() -> None:
    one = (
        "The flow was held at fifty standard cubic centimetres (mL min-1) throughout "
        "the reduction step and the outlet was sampled every minute."
    )
    assert is_front_or_reference_apparatus(one) is False


def test_a_year_alone_is_not_a_citation() -> None:
    """Body prose says `since 2015`. A series name has to be there too."""
    prose = (
        "Since 2015 the reported conductivity of this composition has risen steadily, "
        "which the authors attribute to better control of barium loss."
    )
    assert is_front_or_reference_apparatus(prose) is False


def test_a_lone_file_marker_is_not_a_download_list() -> None:
    one = (
        "The evolution of the defect was recorded continuously and is shown in the "
        "supporting video (AVI), which covers the first two minutes of growth."
    )
    assert is_front_or_reference_apparatus(one) is False
