"""design/127 — Elsevier word-per-line caption join (0.3.45 · rich-v12)."""

from __future__ import annotations

from pathlib import Path

import fitz
from fastapi.testclient import TestClient

from sentence_reading.api.app import app
from sentence_reading.fig_refs import caption_key
from sentence_reading.llm.typography import PIPELINE_VERSION
from sentence_reading.pdf.extract import extract_figures

ROOT = Path(__file__).resolve().parents[1]
EXTRACT = ROOT / "src" / "sentence_reading" / "pdf" / "extract.py"
DESIGN = ROOT / "docs" / "design" / "127-caption-word-join.md"
TYPO = ROOT / "src" / "sentence_reading" / "llm" / "typography.py"
EWBANK = ROOT / "_tmp_ewbank" / "source.pdf"


def _mini_png_bytes() -> bytes:
    pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 100, 80), 1)
    pix.clear_with(170)
    return pix.tobytes("png")


def _insert_words(page, origin: tuple[float, float], words: list[str], *, size: float = 10) -> None:
    """Elsevier-like: each word is its own text write (separate spans/newlines)."""
    x, y = origin
    for w in words:
        page.insert_text((x, y), w, fontsize=size)
        x += max(8.0, len(w) * size * 0.55) + 3.0


def _build_elsevier_style_pdf(path: Path) -> None:
    doc = fitz.open()
    png = _mini_png_bytes()

    page = doc.new_page(width=420, height=640)
    page.insert_image(fitz.Rect(40, 60, 380, 220), stream=png)
    # Word-per-token caption under image.
    _insert_words(
        page,
        (40, 250),
        ["Fig.", "1.", "Word", "joined", "caption", "title"],
    )
    page.insert_text(
        (40, 400),
        "Figure 9 illustrates a body sentence that is not a caption.",
        fontsize=11,
    )

    # Split label crumb + number title (same baseline).
    page2 = doc.new_page(width=420, height=640)
    page2.insert_image(fitz.Rect(40, 60, 380, 240), stream=png)
    page2.insert_text((40, 270), "Fig.", fontsize=11)
    page2.insert_text((70, 270), "4. Split crumb caption title", fontsize=11)

    # Soft table without punct.
    page3 = doc.new_page(width=420, height=640)
    _insert_words(
        page3,
        (40, 80),
        ["Table", "2", "Hydrogen", "consumption", "overview"],
    )

    doc.save(path)
    doc.close()


def test_status_and_pipeline_pin() -> None:
    st = TestClient(app).get("/api/status").json()
    assert st["version"] == "0.3.45"
    assert PIPELINE_VERSION == "rich-v12"
    assert "rich-v12" in TYPO.read_text(encoding="utf-8")
    assert DESIGN.is_file()
    src = EXTRACT.read_text(encoding="utf-8")
    assert "design/127" in src
    assert "_page_caption_lines" in src


def test_elsevier_word_join_extracts_all_labeled(tmp_path: Path) -> None:
    pdf = tmp_path / "elsevier_words.pdf"
    _build_elsevier_style_pdf(pdf)
    figs = extract_figures(pdf)
    keys = {caption_key(f.caption) for f in figs}
    assert "fig:1" in keys
    assert "fig:4" in keys
    assert "table:2" in keys
    assert "fig:9" not in keys


def test_ewbank_pdf_all_labeled_captions_if_present() -> None:
    """Real phone paper: every soft/punct caption key must extract (design/127)."""
    if not EWBANK.is_file():
        return
    from sentence_reading.pdf.extract import (
        _CAPTION_INLINE_START,
        _is_caption_line,
        _page_caption_lines,
    )

    want: set[str] = set()
    doc = fitz.open(EWBANK)
    try:
        for page in doc:
            for text, _rect in _page_caption_lines(page):
                m = _CAPTION_INLINE_START.search(text)
                head = m.group(1).strip() if m else text
                if _is_caption_line(head, fig_scheme=True, table=False) or _is_caption_line(
                    head, fig_scheme=False, table=True
                ):
                    k = caption_key(head)
                    if k:
                        want.add(k)
    finally:
        doc.close()
    assert want, "expected caption keys in Ewbank fixture"
    got = {caption_key(f.caption) for f in extract_figures(EWBANK) if caption_key(f.caption)}
    assert not (want - got), f"missing {want - got}"
