"""design/363 — SI is a cover line above the title, or an SI token in the filename.

A main paper prints Supporting Information after its title (badge, footnote,
methods). It is very hard for that phrase to sit above the title. Searching the
body for the word supplementary is how manabayeva / wang / ChemistryOpen were
called SI: they mention it, they are not it.

`…synthesis1.pdf` and `…methane1.pdf` print `Supporting Information` on line 2,
then the title. Those are SI. Their twins without the trailing `1` print the
title first.
"""

from __future__ import annotations

from pathlib import Path

from sentence_reading.pdf.supplementary_detect import (
    cover_phrase_above_title,
    detect_doc_role_detailed,
    filename_looks_like_si,
)

ROOT = Path(__file__).resolve().parents[1]
DART = ROOT / "mobile/lib/pdf/doc_role_detect.dart"
DESIGN = ROOT / "docs/design/363-cover-above-title.md"


def test_design_363_is_written() -> None:
    text = DESIGN.read_text(encoding="utf-8")
    assert "Status: **locked**" in text
    assert "cover_above_title" in text
    assert "above the title" in text.lower() or "제목보다 위" in text


def test_dart_ports_the_cover_line() -> None:
    dart = DART.read_text(encoding="utf-8")
    assert "cover_above_title" in dart
    assert "coverPhraseAboveTitle" in dart
    assert "supporting\\s+online\\s+materials?" in dart


def test_cover_then_title_is_si() -> None:
    head = (
        "S1\n"
        "Supporting Information\n"
        "Dry Reforming of Methane over Ni-Fe-Al Catalysts Prepared by\n"
        "Solution Combustion Synthesis\n"
    )
    assert cover_phrase_above_title(head) is True
    det = detect_doc_role_detailed(head, filename="paper.pdf")
    assert det.role == "supplementary"
    assert det.reason == "cover_above_title"


def test_title_then_badge_is_main() -> None:
    head = (
        "Dry Reforming of Methane over Ni-Fe-Al Catalysts Prepared by\n"
        "Solution Combustion Synthesis\n"
        "Cite This: Ind. Eng. Chem. Res. 2023, 62, 11439\n"
        "ACCESS\n"
        "Metrics & More\n"
        "Article Recommendations\n"
        "Supporting Information\n"
        "ABSTRACT: Dry reforming of methane (DRM) is a promising method.\n"
    )
    assert cover_phrase_above_title(head) is False
    det = detect_doc_role_detailed(head, filename="paper.pdf")
    assert det.role == "main"
    assert det.reason == "default_main"


def test_a_mention_in_the_body_is_not_a_cover() -> None:
    head = (
        "Catalytic CO2 reduction\n"
        "Abstract\n"
        "Details are given in the Supporting Information.\n"
    )
    assert cover_phrase_above_title(head) is False
    assert detect_doc_role_detailed(head, filename="paper.pdf").role == "main"


def test_science_supporting_online_material() -> None:
    head = (
        "www.sciencemag.org/cgi/content/full/science.1211927/DC1\n"
        "Supporting Online Material for\n"
        "The Origin of OB Runaway Stars\n"
    )
    assert cover_phrase_above_title(head) is True
    det = detect_doc_role_detailed(head, filename="paper.pdf")
    assert det.role == "supplementary"
    assert det.reason == "cover_above_title"


def test_filename_alone_is_enough() -> None:
    head = "Experimental details and catalyst characterization data.\n"
    det = detect_doc_role_detailed(head, filename="1-s2.0-S1385894724017960-mmc1.docx")
    assert det.role == "supplementary"
    assert det.reason == "filename_si"


def test_nature_reprints_the_title_above_the_cover_filename_still_wins() -> None:
    # 41929_2026_1513_MOESM1_ESM: journal, DOI, Article, title, then
    # "Supplementary information". The cover is under the title. The filename
    # still has MOESM / ESM.
    head = (
        "nature catalysis\n"
        "https://doi.org/10.1038/s41929-026-01513-y\n"
        "Article\n"
        "Iron-based single-atom catalysts for\n"
        "selective ammoxidation of C(sp3)-H bonds\n"
        "In the format provided by the\n"
        "authors and unedited\n"
        "Supplementary information\n"
    )
    assert cover_phrase_above_title(head) is False
    det = detect_doc_role_detailed(head, filename="41929_2026_1513_MOESM1_ESM.pdf")
    assert det.role == "supplementary"
    assert det.reason == "filename_si"


def test_acs_badge_then_abstract_is_not_a_cover() -> None:
    head = (
        "ACCESS\n"
        "Metrics & More\n"
        "Article Recommendations\n"
        "Supporting Information\n"
        "ABSTRACT: Methane dry reforming (MDR) converts greenhouse gases.\n"
    )
    assert cover_phrase_above_title(head) is False
    assert detect_doc_role_detailed(head, filename="acsanm.1c00673.pdf").role == "main"


def test_filename_tokens_the_user_named() -> None:
    for name in (
        "cs9b00733_si_001.pdf",
        "d4se00467a1_suppl.pdf",
        "smll71948-sup-0001-suppmat.docx",
        "1-s2.0-S0272884226009739-mmc1.docx",
        "41929_2026_1513_MOESM1_ESM.pdf",
        "fujii.som.pdf",
        "catalysts-2445767-supplementary.pdf",
    ):
        assert filename_looks_like_si(name), name
    assert not filename_looks_like_si(
        "manabayeva-et-al-2023-dry-reforming-of-methane-over-ni-fe-al-"
        "catalysts-prepared-by-solution-combustion-synthesis1.pdf"
    )
