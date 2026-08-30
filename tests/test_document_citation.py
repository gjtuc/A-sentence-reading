"""design/157 — this paper document_citation extraction."""

from __future__ import annotations

from pathlib import Path

import fitz

from sentence_reading.document_citation import (
    extract_document_citation,
    public_document_citation,
)

ROOT = Path(__file__).resolve().parents[1]
DESIGN = ROOT / "docs" / "design" / "157-this-paper-panel.md"


def _title_cover_pdf(path: Path) -> None:
    doc = fitz.open()
    p0 = doc.new_page(width=420, height=560)
    p0.insert_text((40, 80), "Catalytic Dry Reforming of Methane over Ni Catalysts", fontsize=14)
    p0.insert_text((40, 120), "Jane A. Doe, John B. Smith", fontsize=11)
    p0.insert_text((40, 210), "https://doi.org/10.1000/example.doi.157", fontsize=9)
    p0.insert_text((40, 240), "Received 1 January 2024", fontsize=9)
    doc.save(path)
    doc.close()


def test_design_doc_exists() -> None:
    assert DESIGN.is_file()


def test_front_matter_doi_high_confidence(tmp_path: Path) -> None:
    pdf = tmp_path / "t.pdf"
    _title_cover_pdf(pdf)
    doc = fitz.open(pdf)
    pages = [doc.load_page(i).get_text() for i in range(doc.page_count)]
    doc.close()
    full = "\n".join(pages)
    out = extract_document_citation(
        full_text=full,
        pdf_pages=pages,
        title="Catalytic Dry Reforming of Methane over Ni Catalysts",
        title_section_sentences=["Catalytic Dry Reforming of Methane over Ni Catalysts"],
    )
    assert out.get("doi") == "10.1000/example.doi.157"
    assert out.get("source") == "front_matter"
    assert out.get("confidence") == "high"
    assert "Catalytic" in out.get("text", "")


def test_title_only_low_confidence() -> None:
    out = extract_document_citation(
        full_text="Introduction\nWe studied catalysts.",
        pdf_pages=None,
        title="Nickel Catalysts for Dry Reforming of Methane",
        title_section_sentences=["Nickel Catalysts for Dry Reforming of Methane"],
    )
    assert out.get("source") == "title_only"
    assert out.get("confidence") == "low"
    assert out.get("doi") == ""


def test_title_section_doi() -> None:
    out = extract_document_citation(
        full_text="",
        pdf_pages=None,
        title="Short",
        title_section_sentences=[
            "A Long Enough Title For The Paper",
            "doi:10.1016/j.jcat.2019.01.001",
        ],
    )
    assert out.get("doi", "").startswith("10.1016/")
    assert out.get("source") == "title_sentences"


def test_references_doi_not_used() -> None:
    full = (
        "Nickel Catalysts for Dry Reforming\n"
        "Abstract\nBody text.\n\n"
        "References\n"
        "[1] Other Paper doi:10.9999/ref.only\n"
    )
    out = extract_document_citation(
        full_text=full,
        pdf_pages=None,
        title="Nickel Catalysts for Dry Reforming",
        title_section_sentences=["Nickel Catalysts for Dry Reforming"],
    )
    assert out.get("doi", "") != "10.9999/ref.only"
    assert out.get("source") == "title_only"


def test_multi_front_doi_low_confidence() -> None:
    front = (
        "Title Page\n"
        "doi:10.1000/asr.fail.a\n"
        "doi:10.1000/asr.fail.b\n"
    )
    out = extract_document_citation(
        full_text=front + "\nIntroduction\n",
        pdf_pages=[front],
        title="Multi DOI Paper Title Here",
        title_section_sentences=[],
    )
    assert out.get("doi") == "10.1000/asr.fail.a"
    assert out.get("confidence") == "low"


def test_empty_returns_empty() -> None:
    assert extract_document_citation(
        full_text="",
        pdf_pages=None,
        title="x",
        title_section_sentences=[],
    ) == {}


def test_public_document_citation_strips() -> None:
    assert public_document_citation({}) == {}
    assert public_document_citation({"text": "ab"}) == {}
    out = public_document_citation(
        {"text": "Hello World", "doi": "10.1/abc", "source": "front_matter"}
    )
    assert out["text"] == "Hello World"
    assert out["doi"] == "10.1/abc"
