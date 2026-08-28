"""design/150 — column-aware vstack figure composite."""

from __future__ import annotations

import base64
import io
from pathlib import Path
from unittest.mock import MagicMock, patch

import fitz
import pytest
from PIL import Image

from sentence_reading.pdf import azure_layout

ROOT = Path(__file__).resolve().parents[1]


def _png_size(png: bytes) -> tuple[int, int]:
    im = Image.open(io.BytesIO(png))
    return im.size


def test_composite_x_band_left_column() -> None:
    page_rect = fitz.Rect(0, 0, 600, 800)
    fig = fitz.Rect(40, 200, 280, 400)
    cap = fitz.Rect(50, 410, 120, 425)
    x0, x1 = azure_layout._composite_x_band(
        type("P", (), {"rect": page_rect})(),
        fig,
        cap,
    )
    assert x0 <= 50
    assert x1 >= 280
    assert x1 < 500  # left column + bleed, not full page


def test_composite_x_band_full_width_when_spans_gutter() -> None:
    page_rect = fitz.Rect(0, 0, 600, 800)
    fig = fitz.Rect(40, 200, 560, 400)
    cap = fitz.Rect(50, 410, 550, 430)
    x0, x1 = azure_layout._composite_x_band(
        type("P", (), {"rect": page_rect})(),
        fig,
        cap,
    )
    assert x0 <= 6
    assert x1 >= 594


def test_composite_figure_png_column_clamp_not_full_page(tmp_path: Path) -> None:
    pdf = tmp_path / "two_col.pdf"
    doc = fitz.open()
    page = doc.new_page(width=600, height=800)
    shape = page.new_shape()
    shape.draw_rect(fitz.Rect(40, 120, 280, 300))
    shape.finish(color=(0, 0, 0), fill=(0.9, 0.9, 0.9))
    shape.commit()
    page.insert_text((50, 320), "Fig. 1. Left column plot", fontsize=11)
    page.insert_text((320, 140), "Right column Results body text", fontsize=10)
    page.insert_text((320, 160), "More right column PXRD discussion", fontsize=10)
    doc.save(pdf)
    doc.close()

    doc = fitz.open(pdf)
    page = doc[0]
    fig_rect = fitz.Rect(40, 120, 280, 300)
    cap_rect = fitz.Rect(50, 305, 200, 330)
    png = azure_layout._composite_figure_png(page, fig_rect, cap_rect)
    doc.close()
    assert png
    w, _h = _png_size(png)
    assert w < 4800, w
    assert w >= 1500, w


def test_composite_figure_png_caption_above(tmp_path: Path) -> None:
    pdf = tmp_path / "cap_above.pdf"
    doc = fitz.open()
    page = doc.new_page(width=600, height=800)
    page.insert_text((50, 100), "Fig. 3. Operando caption above", fontsize=11)
    shape = page.new_shape()
    shape.draw_rect(fitz.Rect(40, 130, 280, 350))
    shape.finish(color=(0, 0, 0), fill=(0.85, 0.85, 0.85))
    shape.commit()
    doc.save(pdf)
    doc.close()

    doc = fitz.open(pdf)
    page = doc[0]
    fig_rect = fitz.Rect(40, 130, 280, 350)
    cap_rect = fitz.Rect(50, 88, 260, 115)
    png = azure_layout._composite_figure_png(page, fig_rect, cap_rect)
    doc.close()
    assert png
    _w, h = _png_size(png)
    assert h >= 1000


def test_match_fig_caption_above() -> None:
    doc = fitz.open()
    page = doc.new_page(width=600, height=800)
    page.insert_text((50, 100), "Fig. 4. Caption above graph", fontsize=11)
    fig_rect = fitz.Rect(40, 140, 280, 360)
    cap, cap_rect = azure_layout._match_fig_caption_with_rect(page, fig_rect)
    doc.close()
    assert "Fig. 4" in cap
    assert cap_rect is not None
    assert float(cap_rect.y1) <= float(fig_rect.y0) + 8


def test_extract_figures_azure_uses_vstack_composite(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pdf = tmp_path / "paper.pdf"
    doc = fitz.open()
    doc.new_page()
    doc.save(pdf)
    doc.close()

    monkeypatch.setenv("ASR_AZURE_LAYOUT", "1")
    monkeypatch.setenv(
        "AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT",
        "https://test.cognitiveservices.azure.com",
    )
    monkeypatch.setenv("AZURE_DOCUMENT_INTELLIGENCE_KEY", "k")

    composite_png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 40

    mock_figure = MagicMock()
    mock_figure.id = "1.1"
    mock_figure.caption = MagicMock(content="Fig. 1. Test plot")
    mock_figure.bounding_regions = [
        MagicMock(page_number=1, polygon=[0.5, 0.5, 2.0, 0.5, 2.0, 2.0, 0.5, 2.0])
    ]

    mock_result = MagicMock()
    mock_result.model_id = "prebuilt-layout"
    mock_result.figures = [mock_figure]
    mock_result.tables = []

    mock_poller = MagicMock()
    mock_poller.result.return_value = mock_result
    mock_poller.details = {"operation_id": "op-1"}

    mock_client = MagicMock()
    mock_client.begin_analyze_document.return_value = mock_poller
    mock_client.get_analyze_result_figure.return_value = b"\x89PNG\r\n"

    with patch(
        "sentence_reading.pdf.azure_layout._composite_figure_png",
        return_value=composite_png,
    ) as mock_composite:
        with patch(
            "azure.ai.documentintelligence.DocumentIntelligenceClient",
            return_value=mock_client,
        ):
            figs = azure_layout.extract_figures_azure(pdf)

    mock_composite.assert_called_once()
    assert len(figs) == 1
    raw = base64.b64decode(figs[0].image_src.split(",", 1)[1])
    assert raw == composite_png


def test_composite_table_vstack_and_placeholder(tmp_path: Path) -> None:
    import fitz

    from sentence_reading.pdf.composite import composite_table_png, placeholder_png

    pdf = tmp_path / "tbl.pdf"
    doc = fitz.open()
    page = doc.new_page(width=600, height=800)
    page.insert_text((50, 80), "Table 1. Caption above", fontsize=11)
    shape = page.new_shape()
    shape.draw_rect(fitz.Rect(50, 120, 280, 300))
    shape.finish(color=(0, 0, 0), fill=(0.85, 0.85, 0.85))
    shape.commit()
    doc.save(pdf)
    doc.close()

    doc = fitz.open(pdf)
    page = doc[0]
    cap_rect = fitz.Rect(50, 70, 280, 95)
    body_rect = fitz.Rect(50, 120, 280, 300)
    png = composite_table_png(page, body_rect, cap_rect)
    doc.close()
    assert png
    ph = placeholder_png("Table 2 (missing)")
    assert ph.startswith(b"\x89PNG")


def test_composite_table_short_single_line_caption(tmp_path: Path) -> None:
    """Table 1-like — one-line caption box <20pt still renders in vstack."""
    import io

    import fitz
    from PIL import Image

    from sentence_reading.pdf.composite import composite_table_png

    pdf = tmp_path / "tbl_short_cap.pdf"
    doc = fitz.open()
    page = doc.new_page(width=600, height=800)
    page.insert_text((120, 68), "Table 1. Short caption.", fontsize=11)
    shape = page.new_shape()
    shape.draw_rect(fitz.Rect(50, 82, 320, 260))
    shape.finish(color=(0, 0, 0), fill=(0.85, 0.85, 0.85))
    shape.commit()
    doc.save(pdf)
    doc.close()

    doc = fitz.open(pdf)
    page = doc[0]
    cap_rect = fitz.Rect(110, 60, 250, 72)
    body_rect = fitz.Rect(50, 75, 320, 260)
    png = composite_table_png(page, body_rect, cap_rect)
    doc.close()
    assert png

    arr = __import__("numpy").array(Image.open(io.BytesIO(png)).convert("RGB"))
    top = arr[: max(1, arr.shape[0] // 5)]
    assert float(top.mean()) < 250, "caption ink expected in top band of composite"


def test_composite_table_caption_gap_tighter_than_symmetric_pad(tmp_path: Path) -> None:
    """Table vstack — no inflated white band between caption and body."""
    import io

    import fitz
    from PIL import Image

    from sentence_reading.pdf.composite import composite_table_png

    pdf = tmp_path / "tbl_gap.pdf"
    doc = fitz.open()
    page = doc.new_page(width=600, height=800)
    page.insert_text((50, 82), "Table 1. Caption above", fontsize=11)
    shape = page.new_shape()
    shape.draw_rect(fitz.Rect(50, 100, 280, 280))
    shape.finish(color=(0, 0, 0), fill=(0.85, 0.85, 0.85))
    shape.commit()
    doc.save(pdf)
    doc.close()

    doc = fitz.open(pdf)
    page = doc[0]
    cap_rect = fitz.Rect(48, 72, 282, 92)
    body_rect = fitz.Rect(50, 98, 280, 280)
    png = composite_table_png(page, body_rect, cap_rect)
    doc.close()
    assert png

    im = Image.open(io.BytesIO(png)).convert("RGB")
    arr = __import__("numpy").array(im)
    dark = 255 - arr.mean(axis=(1, 2))
    rows = [y for y in range(arr.shape[0]) if dark[y] > 12]
    assert rows
    splits = []
    prev = rows[0]
    run_end = rows[0]
    for y in rows[1:]:
        if y - prev > 6:
            splits.append((run_end, y))
        prev = y
        run_end = y
    assert splits, "expected caption band then table band"
    cap_end, table_start = splits[0]
    white_gap = table_start - cap_end - 1
    assert white_gap <= 12, f"caption-table gap too wide: {white_gap}px"
    im.close()
