# -*- coding: utf-8 -*-
"""design/152 — SI head detection."""

from __future__ import annotations

from sentence_reading.pdf.supplementary_detect import detect_doc_role, normalize_doc_role


def test_detect_supplementary_head() -> None:
    text = (
        "Supplementary Information\n\n"
        "Figure S1. Extra plot\n\n"
        "This SI document contains additional data."
    )
    assert detect_doc_role(text) == "supplementary"


def test_detect_main_abstract() -> None:
    text = (
        "Catalytic CO2 reduction\n\n"
        "Abstract\n\n"
        "We report a novel catalyst for carbon dioxide reduction."
    )
    assert detect_doc_role(text) == "main"


def test_normalize_doc_role() -> None:
    assert normalize_doc_role("si") == "supplementary"
    assert normalize_doc_role("merged") == "main"
    assert normalize_doc_role(None) == "main"


def test_detect_docx_si_filename() -> None:
    text = "Experimental details and catalyst characterization data."
    role = detect_doc_role(
        text,
        filename="차완_논문__1-s2.0-S1385894724017960-mmc1 (2).docx",
    )
    assert role == "supplementary"

    role2 = detect_doc_role(
        text,
        filename="차완_논문__smll71948-sup-0001-suppmat.docx",
    )
    assert role2 == "supplementary"


def test_detect_table_fig_si() -> None:
    text = "Some intro text.\nTable S1. Textural properties of catalysts.\nFigure S1. XRD patterns."
    role = detect_doc_role(text, filename="1-s2.0-S1385894724017960-mmc1.pdf")
    assert role == "supplementary"
