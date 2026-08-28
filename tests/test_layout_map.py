"""design/151 — layout_map build + persist."""

from __future__ import annotations

import json
from pathlib import Path

from sentence_reading.pdf.layout_map import (
    LayoutBox,
    LayoutMap,
    build_layout_map_from_result,
    load_layout_map,
    polygon_to_rect,
    save_layout_map,
)


class _FakeBR:
    def __init__(self, page: int, polygon: list[float]) -> None:
        self.page_number = page
        self.polygon = polygon


class _FakePara:
    def __init__(self, text: str, page: int, polygon: list[float]) -> None:
        self.content = text
        self.bounding_regions = [_FakeBR(page, polygon)]


class _FakeResult:
    model_id = "prebuilt-layout"
    paragraphs = []
    figures = []
    tables = []


def test_polygon_to_rect_inches_to_pt() -> None:
    rect = polygon_to_rect([0.0, 0.0, 1.0, 0.0, 1.0, 1.0, 0.0, 1.0])
    assert rect is not None
    assert rect["x1"] == 72.0
    assert rect["y1"] == 72.0


def test_build_layout_map_paragraph_caption(tmp_path: Path) -> None:
    import fitz

    pdf = tmp_path / "t.pdf"
    doc = fitz.open()
    doc.new_page(width=612, height=792)
    doc.save(pdf)
    doc.close()
    doc = fitz.open(pdf)
    result = _FakeResult()
    result.paragraphs = [
        _FakePara("Fig. 1. XRD patterns", 1, [0.1, 0.5, 0.9, 0.5, 0.9, 0.55, 0.1, 0.55]),
        _FakePara("Results body text continues here.", 1, [0.1, 0.2, 0.9, 0.2, 0.9, 0.3, 0.1, 0.3]),
    ]
    layout = build_layout_map_from_result(result, doc)
    doc.close()
    kinds = {b.kind for b in layout.boxes}
    assert "figure_caption" in kinds
    assert "paragraph" in kinds


def test_save_load_layout_map(tmp_path: Path) -> None:
    layout = LayoutMap(
        pages=[{"page_index": 0, "width_pt": 612, "height_pt": 792}],
        boxes=[
            LayoutBox(
                id="p-0001",
                page_index=0,
                kind="paragraph",
                rect={"x0": 1, "y0": 2, "x1": 3, "y1": 4},
                text="hello",
            )
        ],
    )
    save_layout_map(tmp_path, layout)
    loaded = load_layout_map(tmp_path)
    assert loaded is not None
    assert loaded.boxes[0].text == "hello"
    raw = json.loads((tmp_path / "layout_map.json").read_text(encoding="utf-8"))
    assert raw["version"] == 1
