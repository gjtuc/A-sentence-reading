"""
design/151 — Azure analyze → LayoutMap JSON (single analyze, reused downstream).
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

_INCH_TO_PT = 72.0
_LAYOUT_MAP_NAME = "layout_map.json"


@dataclass
class LayoutBox:
    id: str
    page_index: int
    kind: str
    rect: dict[str, float]
    text: str = ""
    azure_ref: str = ""
    used_by_slot: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "page_index": self.page_index,
            "kind": self.kind,
            "rect": dict(self.rect),
            "text": self.text,
            "azure_ref": self.azure_ref,
            "used_by_slot": self.used_by_slot,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> LayoutBox:
        rect = raw.get("rect") or {}
        return cls(
            id=str(raw.get("id") or ""),
            page_index=int(raw.get("page_index") or 0),
            kind=str(raw.get("kind") or "paragraph"),
            rect={
                "x0": float(rect.get("x0") or 0),
                "y0": float(rect.get("y0") or 0),
                "x1": float(rect.get("x1") or 0),
                "y1": float(rect.get("y1") or 0),
            },
            text=str(raw.get("text") or ""),
            azure_ref=str(raw.get("azure_ref") or ""),
            used_by_slot=str(raw.get("used_by_slot") or ""),
        )


@dataclass
class LayoutMap:
    pages: list[dict[str, Any]] = field(default_factory=list)
    boxes: list[LayoutBox] = field(default_factory=list)
    operation_id: str = ""
    model_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": 1,
            "operation_id": self.operation_id,
            "model_id": self.model_id,
            "pages": list(self.pages),
            "boxes": [b.to_dict() for b in self.boxes],
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> LayoutMap:
        boxes = [
            LayoutBox.from_dict(b)
            for b in (raw.get("boxes") or [])
            if isinstance(b, dict)
        ]
        return cls(
            pages=[p for p in (raw.get("pages") or []) if isinstance(p, dict)],
            boxes=boxes,
            operation_id=str(raw.get("operation_id") or ""),
            model_id=str(raw.get("model_id") or ""),
        )

    def box_by_id(self, box_id: str) -> LayoutBox | None:
        bid = (box_id or "").strip()
        for b in self.boxes:
            if b.id == bid:
                return b
        return None

    def boxes_on_page(self, page_index: int) -> list[LayoutBox]:
        return [b for b in self.boxes if b.page_index == page_index]

    def unused_boxes(self, kind: str | None = None) -> list[LayoutBox]:
        out: list[LayoutBox] = []
        for b in self.boxes:
            if b.used_by_slot:
                continue
            if kind is not None and b.kind != kind:
                continue
            out.append(b)
        return out


def polygon_to_rect(polygon: list[float] | None) -> dict[str, float] | None:
    if not polygon or len(polygon) < 8:
        return None
    xs = [float(polygon[i]) for i in range(0, len(polygon), 2)]
    ys = [float(polygon[i]) for i in range(1, len(polygon), 2)]
    return {
        "x0": min(xs) * _INCH_TO_PT,
        "y0": min(ys) * _INCH_TO_PT,
        "x1": max(xs) * _INCH_TO_PT,
        "y1": max(ys) * _INCH_TO_PT,
    }


def _region_page_and_rect(bounding_regions) -> tuple[int | None, dict[str, float] | None]:
    if not bounding_regions:
        return None, None
    br = bounding_regions[0]
    page_num = int(getattr(br, "page_number", None) or 1)
    page_index = page_num - 1
    polygon = list(getattr(br, "polygon", None) or [])
    return page_index, polygon_to_rect(polygon)


def _figure_caption_text(figure) -> str:
    cap = getattr(figure, "caption", None)
    if cap is None:
        return ""
    return (getattr(cap, "content", None) or "").strip()


def _classify_paragraph_caption(text: str) -> str | None:
    from sentence_reading.pdf.extract import _CAPTION_LABEL, _is_caption_line, _normalize_caption

    raw = _normalize_caption(text)
    if not raw:
        return None
    m = _CAPTION_LABEL.match(raw)
    if not m:
        return None
    label = m.group(0).lower()
    if "table" in label:
        return "table_caption" if _is_caption_line(raw, fig_scheme=False, table=True) else None
    if _is_caption_line(raw, fig_scheme=True, table=False):
        return "figure_caption"
    return None


def build_layout_map_from_result(result, doc) -> LayoutMap:
    """Map Azure prebuilt-layout result + PyMuPDF doc pages → LayoutMap."""
    import fitz

    pages: list[dict[str, Any]] = []
    for i in range(len(doc)):
        page = doc[i]
        pages.append(
            {
                "page_index": i,
                "width_pt": float(page.rect.width),
                "height_pt": float(page.rect.height),
            }
        )

    boxes: list[LayoutBox] = []
    seq = 0

    for para in result.paragraphs or []:
        page_index, rect = _region_page_and_rect(
            getattr(para, "bounding_regions", None) or []
        )
        if page_index is None or rect is None:
            continue
        text = (getattr(para, "content", None) or "").strip()
        kind = _classify_paragraph_caption(text) or "paragraph"
        seq += 1
        boxes.append(
            LayoutBox(
                id=f"p-{seq:04d}",
                page_index=page_index,
                kind=kind,
                rect=rect,
                text=text,
            )
        )

    for figure in result.figures or []:
        page_index, rect = _region_page_and_rect(
            getattr(figure, "bounding_regions", None) or []
        )
        if page_index is None or rect is None:
            continue
        fig_id = str(getattr(figure, "id", None) or "")
        cap_text = _figure_caption_text(figure)
        seq += 1
        boxes.append(
            LayoutBox(
                id=f"fb-{seq:04d}",
                page_index=page_index,
                kind="figure_body",
                rect=rect,
                text="",
                azure_ref=fig_id,
            )
        )
        if cap_text:
            seq += 1
            boxes.append(
                LayoutBox(
                    id=f"fc-{seq:04d}",
                    page_index=page_index,
                    kind="figure_caption",
                    rect=rect,
                    text=cap_text,
                    azure_ref=fig_id,
                )
            )

    for table in result.tables or []:
        page_index, rect = _region_page_and_rect(
            getattr(table, "bounding_regions", None) or []
        )
        if page_index is None or rect is None:
            continue
        tbl_id = str(getattr(table, "id", None) or "")
        seq += 1
        boxes.append(
            LayoutBox(
                id=f"tb-{seq:04d}",
                page_index=page_index,
                kind="table_body",
                rect=rect,
                text="",
                azure_ref=tbl_id,
            )
        )

    return LayoutMap(
        pages=pages,
        boxes=boxes,
        operation_id="",
        model_id=str(getattr(result, "model_id", None) or ""),
    )


def analyze_layout_map(pdf_path: Path) -> tuple[LayoutMap, object, object]:
    """
    Single Azure analyze. Returns (layout_map, azure_client, analyze_result).
    Caller must close PyMuPDF doc separately.
    """
    from azure.ai.documentintelligence import DocumentIntelligenceClient
    from azure.ai.documentintelligence.models import AnalyzeOutputOption
    from azure.core.credentials import AzureKeyCredential

    from sentence_reading.llm.env import (
        azure_document_intelligence_available,
        azure_document_intelligence_endpoint,
        azure_document_intelligence_key,
    )
    from sentence_reading.pdf.azure_layout import _timeout_s

    if not azure_document_intelligence_available():
        raise RuntimeError("azure_document_intelligence_not_configured")

    import fitz

    endpoint = azure_document_intelligence_endpoint() or ""
    key = azure_document_intelligence_key() or ""
    client = DocumentIntelligenceClient(
        endpoint=endpoint,
        credential=AzureKeyCredential(key),
    )
    doc = fitz.open(pdf_path)
    try:
        with pdf_path.open("rb") as pdf_file:
            poller = client.begin_analyze_document(
                "prebuilt-layout",
                body=pdf_file,
                output=[AnalyzeOutputOption.FIGURES],
            )
        result = poller.result(timeout=_timeout_s())
        operation_id = str(poller.details.get("operation_id") or "")
        layout = build_layout_map_from_result(result, doc)
        layout.operation_id = operation_id
        return layout, client, result
    finally:
        doc.close()


def save_layout_map(paper_dir: Path, layout_map: LayoutMap) -> Path:
    paper_dir.mkdir(parents=True, exist_ok=True)
    out = paper_dir / _LAYOUT_MAP_NAME
    out.write_text(
        json.dumps(layout_map.to_dict(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return out


def load_layout_map(paper_dir: Path) -> LayoutMap | None:
    path = paper_dir / _LAYOUT_MAP_NAME
    if not path.is_file():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(raw, dict):
        return None
    return LayoutMap.from_dict(raw)


def read_figure_png(client, *, model_id: str, result_id: str, figure_id: str) -> bytes:
    resp = client.get_analyze_result_figure(
        model_id=model_id,
        result_id=result_id,
        figure_id=figure_id,
    )
    if isinstance(resp, (bytes, bytearray)):
        return bytes(resp)
    return b"".join(resp)
