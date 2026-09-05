"""design/135 — title-page cover as carousel figure 1 (0.3.85 · rich-v24)."""

from __future__ import annotations

import os
from pathlib import Path

import fitz
from fastapi.testclient import TestClient

from sentence_reading.api.app import app
from sentence_reading.llm.typography import PIPELINE_VERSION
from sentence_reading.pdf.extract import (
    _caption_sort_key,
    extract_figures,
    page_text_looks_like_title_cover,
)

ROOT = Path(__file__).resolve().parents[1]
DESIGN = ROOT / "docs" / "design" / "135-cover-as-figure.md"
TYPO = ROOT / "src" / "sentence_reading" / "llm" / "typography.py"
PUB = ROOT / "mobile" / "pubspec.yaml"


def _mini_png_bytes() -> bytes:
    pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 80, 60), 1)
    pix.clear_with(160)
    return pix.tobytes("png")


def _title_cover_pdf(path: Path) -> None:
    """Page 0 looks like a journal title page; page 1 has Fig. 1."""
    doc = fitz.open()
    png = _mini_png_bytes()
    p0 = doc.new_page(width=420, height=560)
    p0.insert_text((40, 80), "Catalytic Dry Reforming of Methane over Ni Catalysts", fontsize=14)
    p0.insert_text((40, 120), "Jane A. Doe, John B. Smith", fontsize=11)
    p0.insert_text((40, 150), "Department of Chemical Engineering, Example University", fontsize=10)
    p0.insert_text((40, 180), "Corresponding author: jane@example.edu", fontsize=10)
    p0.insert_text((40, 210), "https://doi.org/10.1000/example.doi.135", fontsize=9)
    p0.insert_text((40, 240), "Received 1 January 2024; Accepted 2 February 2024", fontsize=9)
    p0.insert_text((40, 280), "Abstract", fontsize=12)
    p0.insert_text(
        (40, 310),
        "We report a mock abstract for cover heuristic tests only.",
        fontsize=10,
    )

    p1 = doc.new_page(width=420, height=560)
    p1.insert_image(fitz.Rect(40, 60, 200, 180), stream=png)
    p1.insert_text((40, 200), "Fig. 1. Mock catalyst scheme for cover chip.", fontsize=11)
    doc.save(path)
    doc.close()


def _body_only_pdf(path: Path) -> None:
    """Page 0 opens like Introduction — must not invent a cover."""
    doc = fitz.open()
    png = _mini_png_bytes()
    p0 = doc.new_page(width=420, height=560)
    p0.insert_text((40, 80), "1. Introduction", fontsize=14)
    p0.insert_text(
        (40, 120),
        "This page is body text without title or author front matter. " * 8,
        fontsize=10,
    )
    p0.insert_image(fitz.Rect(40, 320, 200, 440), stream=png)
    p0.insert_text((40, 460), "Fig. 1. Body-adjacent figure.", fontsize=11)
    doc.save(path)
    doc.close()


def test_status_and_docs_pin_cover_chip():
    st = TestClient(app).get("/api/status").json()
    assert st["version"] == "0.3.156"
    assert st["pipeline_version"] == "rich-v24"
    assert st["cover_as_figure"] is True
    assert st["mobile_cover_as_figure"] is True
    assert PIPELINE_VERSION == "rich-v24"
    assert "rich-v24" in TYPO.read_text(encoding="utf-8")
    assert "0.3.156" in PUB.read_text(encoding="utf-8")
    assert DESIGN.is_file()
    assert "ASR_COVER_AS_FIGURE" in DESIGN.read_text(encoding="utf-8")


def test_title_page_sort_key_before_ga_and_fig():
    caps = [
        "Fig. 1. Scheme",
        "Graphical abstract (p.1)",
        "Title page (p.1)",
        "Table 1. Data",
    ]
    ordered = sorted(caps, key=_caption_sort_key)
    assert ordered[0].startswith("Title page")
    assert ordered[1].startswith("Graphical abstract")


def test_heuristic_accepts_title_author_rejects_body_and_empty():
    coverish = (
        "Catalytic Dry Reforming of Methane over Ni Catalysts\n"
        "Jane A. Doe, John B. Smith\n"
        "Department of Chemical Engineering, Example University\n"
        "Corresponding author: jane@example.edu\n"
        "https://doi.org/10.1000/example.doi.135\n"
        "Abstract\nWe report a mock abstract.\n"
    )
    assert page_text_looks_like_title_cover(coverish) is True
    assert page_text_looks_like_title_cover("") is False
    assert page_text_looks_like_title_cover("short") is False
    body = (
        "1. Introduction\n"
        "This chapter continues mid-paper body text without authors. " * 6
    )
    assert page_text_looks_like_title_cover(body) is False
    # EDGE: path traversal / nulls must not crash or force True.
    assert page_text_looks_like_title_cover("../etc/passwd\x00" + ("x" * 80)) is False


def test_extract_prepends_title_cover(tmp_path: Path):
    pdf = tmp_path / "cover.pdf"
    _title_cover_pdf(pdf)
    figs = extract_figures(pdf)
    assert figs, "expected at least cover + fig"
    assert figs[0].caption.startswith("Title page")
    assert figs[0].page_index == 0
    assert figs[0].image_src.startswith("data:image/png;base64,")
    # Fig. 1 still present somewhere after cover.
    assert any("Fig. 1" in (f.caption or "") for f in figs[1:])


def test_extract_skips_cover_on_body_page(tmp_path: Path):
    pdf = tmp_path / "body.pdf"
    _body_only_pdf(pdf)
    figs = extract_figures(pdf)
    assert all(not (f.caption or "").lower().startswith("title page") for f in figs)


def test_kill_switch_skips_cover(tmp_path: Path, monkeypatch):
    pdf = tmp_path / "cover_kill.pdf"
    _title_cover_pdf(pdf)
    monkeypatch.setenv("ASR_COVER_AS_FIGURE", "0")
    figs = extract_figures(pdf)
    assert all(not (f.caption or "").lower().startswith("title page") for f in figs)
    # Status flag follows kill.
    st = TestClient(app).get("/api/status").json()
    assert st["cover_as_figure"] is False
