"""design/126 — soft caption labels without required punct (0.3.51 · rich-v15)."""

from __future__ import annotations

from pathlib import Path

import fitz
from fastapi.testclient import TestClient

from sentence_reading.api.app import app
from sentence_reading.fig_refs import caption_key
from sentence_reading.llm.typography import PIPELINE_VERSION
from sentence_reading.pdf.extract import _is_caption_line, extract_figures

ROOT = Path(__file__).resolve().parents[1]
EXTRACT = ROOT / "src" / "sentence_reading" / "pdf" / "extract.py"
DESIGN = ROOT / "docs" / "design" / "126-soft-caption-labels.md"
TYPO = ROOT / "src" / "sentence_reading" / "llm" / "typography.py"


def _mini_png_bytes() -> bytes:
    pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 80, 60), 1)
    pix.clear_with(160)
    return pix.tobytes("png")


def _build_soft_caption_pdf(path: Path) -> None:
    """
    Soft captions (no punct after number) + body sentence that must be rejected.
    """
    doc = fitz.open()
    png = _mini_png_bytes()

    page = doc.new_page(width=420, height=560)
    page.insert_image(fitz.Rect(40, 60, 200, 180), stream=png)
    page.insert_text((40, 200), "Fig. 1 Soft title without punct", fontsize=11)
    page.insert_image(fitz.Rect(220, 60, 380, 180), stream=png)
    page.insert_text((220, 200), "Figure 2 Another soft caption", fontsize=11)
    page.insert_text((40, 280), "Scheme 1 Synthesis overview", fontsize=11)
    page.insert_text((40, 320), "Table 1 Soft table title here", fontsize=11)
    page.insert_text(
        (40, 420),
        "Figure 9 illustrates a body sentence that is not a caption.",
        fontsize=11,
    )
    page.insert_text(
        (40, 460),
        "Fig. 8 shows another body-like false positive.",
        fontsize=11,
    )

    # Orphan soft caption (vector-like)
    page2 = doc.new_page(width=420, height=560)
    shape = page2.new_shape()
    shape.draw_rect(fitz.Rect(50, 80, 370, 240))
    shape.finish(color=(0.1, 0.2, 0.5), fill=(0.9, 0.92, 1.0))
    shape.commit()
    page2.insert_text((50, 270), "Fig. 3 Soft orphan caption title", fontsize=11)

    doc.save(path)
    doc.close()


def test_status_and_pipeline_pin() -> None:
    st = TestClient(app).get("/api/status").json()
    assert st["version"] == "0.3.57"
    assert PIPELINE_VERSION == "rich-v15"
    assert "rich-v15" in TYPO.read_text(encoding="utf-8")
    assert DESIGN.is_file()
    src = EXTRACT.read_text(encoding="utf-8")
    assert "design/126" in src
    assert "_is_caption_line" in src
    assert "_BODY_AFTER_LABEL" in src


def test_is_caption_line_soft_vs_body() -> None:
    assert _is_caption_line("Fig. 1 Soft title", fig_scheme=True, table=False)
    assert _is_caption_line("Fig. 1. Punct still ok", fig_scheme=True, table=False)
    assert _is_caption_line("Table 2 Soft table", fig_scheme=False, table=True)
    assert not _is_caption_line(
        "Figure 9 illustrates a body sentence", fig_scheme=True, table=False
    )
    assert not _is_caption_line(
        "Fig. 8 shows another body-like false positive.",
        fig_scheme=True,
        table=False,
    )


def test_soft_captions_extract_and_reject_body(tmp_path: Path) -> None:
    pdf = tmp_path / "soft_captions.pdf"
    _build_soft_caption_pdf(pdf)
    figs = extract_figures(pdf)
    keys = {caption_key(f.caption) for f in figs}
    assert "fig:1" in keys
    assert "fig:2" in keys
    assert "fig:3" in keys
    assert "scheme:1" in keys
    assert "table:1" in keys
    assert "fig:9" not in keys
    assert "fig:8" not in keys
    assert all(f.image_src.startswith("data:image/png") for f in figs)
