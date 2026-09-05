"""design/128 — column-wide orphan table/fig clips (0.3.51 · rich-v24)."""

from __future__ import annotations

from pathlib import Path

import fitz
from fastapi.testclient import TestClient

from sentence_reading.api.app import app
from sentence_reading.fig_refs import caption_key
from sentence_reading.llm.typography import PIPELINE_VERSION
from sentence_reading.pdf.extract import (
    _column_x_range,
    _orphan_table_clip,
    extract_figures,
)

ROOT = Path(__file__).resolve().parents[1]
EXTRACT = ROOT / "src" / "sentence_reading" / "pdf" / "extract.py"
DESIGN = ROOT / "docs" / "design" / "128-clip-column-width.md"
TYPO = ROOT / "src" / "sentence_reading" / "llm" / "typography.py"
EWBANK = ROOT / "_tmp_ewbank" / "source.pdf"


def test_status_and_pipeline_pin() -> None:
    st = TestClient(app).get("/api/status").json()
    assert st["version"] == "0.3.156"
    assert PIPELINE_VERSION == "rich-v24"
    assert "rich-v24" in TYPO.read_text(encoding="utf-8")
    assert DESIGN.is_file()
    src = EXTRACT.read_text(encoding="utf-8")
    assert "design/128" in src
    assert "_column_x_range" in src


def test_narrow_caption_gets_column_width() -> None:
    page_rect = fitz.Rect(0, 0, 600, 800)
    # Narrow caption on left column.
    cap = fitz.Rect(40, 60, 90, 75)
    x0, x1 = _column_x_range(page_rect, cap, bleed_frac=0.10)
    assert x0 <= 40
    assert x1 >= 300  # crosses mid (300) with bleed
    clip = _orphan_table_clip(
        type("P", (), {"rect": page_rect})(),
        cap,
    )
    assert clip.width >= 250


def test_synthetic_wide_table_not_caption_thin(tmp_path: Path) -> None:
    """Narrow 'Table 1.' caption under a wide left-column table drawing."""
    pdf = tmp_path / "wide_table.pdf"
    doc = fitz.open()
    page = doc.new_page(width=600, height=800)
    # Wide table frame in left column.
    shape = page.new_shape()
    shape.draw_rect(fitz.Rect(30, 100, 290, 320))
    for y in (140, 180, 220, 260, 300):
        shape.draw_line(fitz.Point(30, y), fitz.Point(290, y))
    for x in (90, 150, 210):
        shape.draw_line(fitz.Point(x, 100), fitz.Point(x, 320))
    shape.finish(color=(0, 0, 0), width=0.8)
    shape.commit()
    page.insert_text((40, 90), "Table 1. Wide synthetic metrics", fontsize=11)
    # Right column body (bleed OK if present).
    page.insert_text((320, 120), "Right column body text should be optional bleed.", fontsize=10)
    doc.save(pdf)
    doc.close()

    figs = extract_figures(pdf)
    tables = [f for f in figs if (caption_key(f.caption) or "").startswith("table:")]
    assert tables, "expected a table figure"
    import base64

    raw = base64.b64decode(tables[0].image_src.split(",", 1)[1])
    pix = fitz.Pixmap(raw)
    # zoom=8 → column ~300pt => width should be well above narrow caption (~50*8).
    assert pix.width >= 1800, pix.width


def test_ewbank_tables_render_wide_if_present() -> None:
    if not EWBANK.is_file():
        return
    import base64

    figs = extract_figures(EWBANK)
    tables = [f for f in figs if (caption_key(f.caption) or "").startswith("table:")]
    assert len(tables) >= 1
    for f in tables:
        raw = base64.b64decode(f.image_src.split(",", 1)[1])
        pix = fitz.Pixmap(raw)
        # Page ~595pt, column band ~ half + bleed, zoom 8 → expect wide raster.
        assert pix.width >= 2000, (caption_key(f.caption), pix.width)
