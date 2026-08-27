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
