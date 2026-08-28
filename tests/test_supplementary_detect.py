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
