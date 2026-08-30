"""partial slot orphan fallback when Azure misses figure body (0.3.92)."""

from __future__ import annotations

import base64
import io
from pathlib import Path
from unittest.mock import MagicMock, patch

import fitz
import pytest
from PIL import Image

from sentence_reading.fig_refs import caption_key
from sentence_reading.llm.env import azure_document_intelligence_available
from sentence_reading.pdf.extract import (
    extract_figures,
    is_caption_only_figure_png,
    orphan_figure_png_from_caption,
)
from sentence_reading.pdf.extract_figures_v2 import _render_slot_png
from sentence_reading.pdf.layout_map import LayoutBox, LayoutMap
from sentence_reading.pdf.slot_plan import Slot

ACSANM = Path(r"C:\Users\user\Desktop\은규 논문\acsanm.1c00673.pdf")


def _strip_png(width: int = 2419, height: int = 191) -> bytes:
    im = Image.new("RGB", (width, height))
    px = im.load()
    for y in range(height):
        for x in range(0, width, 17):
            px[x, y] = (x % 255, y % 255, 40)
    buf = io.BytesIO()
    im.save(buf, format="PNG")
    data = buf.getvalue()
    assert len(data) >= 2_000
    return data


def _png_height(png: bytes) -> int:
    return Image.open(io.BytesIO(png)).size[1]


def _figure_png(fig) -> bytes:
    src = fig.image_src or ""
    if src.startswith("data:image/png;base64,"):
        return base64.b64decode(src.split(",", 1)[1])
    return b""


def test_is_caption_only_strip() -> None:
    assert is_caption_only_figure_png(_strip_png()) is True
    assert is_caption_only_figure_png(_strip_png(800, 600)) is False
    assert is_caption_only_figure_png(b"short") is False


def test_orphan_figure_png_from_caption(tmp_path: Path) -> None:
    pdf = tmp_path / "orphan.pdf"
    doc = fitz.open()
    page = doc.new_page(width=400, height=500)
    shape = page.new_shape()
    shape.draw_rect(fitz.Rect(60, 100, 340, 260))
    shape.finish(color=(0.2, 0.2, 0.6), fill=(0.85, 0.9, 1.0))
    shape.commit()
    page.insert_text((60, 295), "Fig. 3. Vector orphan.", fontsize=11)
    doc.save(pdf)
    doc.close()

    doc = fitz.open(pdf)
    try:
        page = doc[0]
        hits = page.search_for("Fig. 3")
        cap = hits[0] if hits else fitz.Rect(60, 280, 340, 300)
        png = orphan_figure_png_from_caption(page, cap)
        assert png is not None
        assert _png_height(png) > 400
    finally:
        doc.close()


def test_render_slot_png_partial_uses_orphan() -> None:
    doc = fitz.open()
    page = doc.new_page(width=400, height=500)
    shape = page.new_shape()
    shape.draw_rect(fitz.Rect(60, 100, 340, 260))
    shape.finish(color=(0.2, 0.2, 0.6), fill=(0.85, 0.9, 1.0))
    shape.commit()
    page.insert_text((60, 295), "Fig. 3. Test caption.", fontsize=11)

    layout = LayoutMap(
        boxes=[
            LayoutBox(
                id="p-cap",
                page_index=0,
                kind="figure_caption",
                rect={"x0": 60, "y0": 280, "x1": 340, "y1": 300},
                text="Fig. 3. Test caption.",
            ),
        ]
    )
    slot = Slot(
        key="fig:3",
        kind="fig",
        n=3,
        status="partial",
        caption_box_id="p-cap",
        caption_text="Fig. 3. Test caption.",
    )

    strip = _strip_png()
    orphan_called = {"count": 0}
    real_orphan = orphan_figure_png_from_caption

    def _track_orphan(pg, cap):
        orphan_called["count"] += 1
        return real_orphan(pg, cap)

    with patch(
        "sentence_reading.pdf.extract_figures_v2.composite_figure_png",
        return_value=strip,
    ), patch(
        "sentence_reading.pdf.extract_figures_v2.orphan_figure_png_from_caption",
        side_effect=_track_orphan,
    ):
        png, caption, page_index = _render_slot_png(doc, MagicMock(), layout, slot)

    doc.close()
    assert orphan_called["count"] == 1
    assert _png_height(png) > 400
    assert page_index == 0
    assert "Fig. 3" in caption


def test_filled_slot_unchanged() -> None:
    doc = fitz.open()
    doc.new_page(width=400, height=500)

    layout = LayoutMap(
        boxes=[
            LayoutBox(
                id="fb",
                page_index=0,
                kind="figure",
                rect={"x0": 60, "y0": 100, "x1": 340, "y1": 260},
            ),
            LayoutBox(
                id="p-cap",
                page_index=0,
                kind="figure_caption",
                rect={"x0": 60, "y0": 280, "x1": 340, "y1": 300},
                text="Fig. 5. Filled.",
            ),
        ]
    )
    slot = Slot(
        key="fig:5",
        kind="fig",
        n=5,
        status="filled",
        body_box_id="fb",
        caption_box_id="p-cap",
        caption_text="Fig. 5. Filled.",
    )

    good_png = _strip_png(800, 600)

    with patch(
        "sentence_reading.pdf.extract_figures_v2.composite_figure_png",
        return_value=good_png,
    ) as mock_comp, patch(
        "sentence_reading.pdf.extract_figures_v2.orphan_figure_png_from_caption",
    ) as mock_orphan:
        png, _, _ = _render_slot_png(doc, MagicMock(), layout, slot)

    doc.close()
    mock_comp.assert_called_once()
    mock_orphan.assert_not_called()
    assert png == good_png


@pytest.mark.skipif(not ACSANM.is_file(), reason="acsanm PDF not on disk")
@pytest.mark.skipif(
    not azure_document_intelligence_available(),
    reason="Azure Document Intelligence credentials not configured",
)
def test_acsanm_fig3_orphan_integration(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ASR_AZURE_LAYOUT", "1")

    figs = extract_figures(ACSANM)
    by_key = {caption_key(f.caption): f for f in figs if caption_key(f.caption)}

    fig3 = by_key.get("fig:3")
    assert fig3 is not None
    assert _png_height(_figure_png(fig3)) > 1000

    fig5 = by_key.get("fig:5")
    assert fig5 is not None
    assert _png_height(_figure_png(fig5)) > 400
