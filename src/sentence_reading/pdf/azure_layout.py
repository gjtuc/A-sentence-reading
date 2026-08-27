"""
Azure Document Intelligence prebuilt-layout → Figure[] (design/147 · 149 · 150).

WHY: PyMuPDF caption-first clips miss vector figures and bleed into adjacent tables.
Uses layout model figures output + table bboxes with PyMuPDF raster for tables.
design/149 — filter Azure body captions; composite fig+caption PNG.
design/150 — column clamp + vstack composite (no rect|cap_rect union).
"""

from __future__ import annotations

import logging
import os
import re
from pathlib import Path

from sentence_reading.models import Figure

log = logging.getLogger(__name__)

_INCH_TO_PT = 72.0
_AZURE_CAPTION_MAX_CHARS = 140
_AZURE_BODY_REST = re.compile(
    r"^(of|with|while|the|a|and|or|at|in|on|for|from|to)\b",
    re.IGNORECASE,
)
_AZURE_PERCENT = re.compile(r"\d+\.\d+\s*%")
_FULL_WIDTH_FRAC = 0.55
_CAPTION_PAIR_BELOW_PT = 160.0
_CAPTION_PAIR_ABOVE_PT = 120.0


def _rect_spans_gutter(page_rect, rect) -> bool:
    """True when rect crosses page midpoint (full-width figure/caption)."""
    mid = (float(page_rect.x0) + float(page_rect.x1)) / 2.0
    x0, x1 = float(rect.x0), float(rect.x1)
    return x0 < mid - 2 and x1 > mid + 2


def _composite_x_band(page, fig_rect, cap_rect) -> tuple[float, float]:
    """design/150 — column band or full page width for composite clips."""
    from sentence_reading.pdf.extract import _column_x_range

    page_rect = page.rect
    anchor = cap_rect if cap_rect is not None else fig_rect
    if anchor is None:
        pad = 6.0
        return float(page_rect.x0) + pad, float(page_rect.x1) - pad

    width_frac = float(anchor.width) / max(float(page_rect.width), 1.0)
    if _rect_spans_gutter(page_rect, anchor) or width_frac > _FULL_WIDTH_FRAC:
        pad = 6.0
        return float(page_rect.x0) + pad, float(page_rect.x1) - pad

    if fig_rect is not None and (
        _rect_spans_gutter(page_rect, fig_rect)
        or float(fig_rect.width) / max(float(page_rect.width), 1.0) > _FULL_WIDTH_FRAC
    ):
        pad = 6.0
        return float(page_rect.x0) + pad, float(page_rect.x1) - pad

    return _column_x_range(page_rect, anchor, bleed_frac=0.08)


def _clamp_rect_x(rect, x0: float, x1: float):
    """Intersect rect with column x band; preserve y."""
    import fitz

    r = fitz.Rect(rect)
    r.x0 = max(float(r.x0), x0)
    r.x1 = min(float(r.x1), x1)
    if r.x1 <= r.x0 + 1:
        return None
    return r


def _vstack_pngs(strips: list[bytes]) -> bytes | None:
    """Stack PNG byte strips vertically; equalize width on white canvas."""
    import io

    from PIL import Image

    images: list[Image.Image] = []
    try:
        for raw in strips:
            if not raw:
                continue
            im = Image.open(io.BytesIO(raw)).convert("RGB")
            if im.width < 4 or im.height < 4:
                continue
            images.append(im)
        if not images:
            return None
        if len(images) == 1:
            out = io.BytesIO()
            images[0].save(out, format="PNG")
            return out.getvalue()

        max_w = max(im.width for im in images)
        total_h = sum(im.height for im in images)
        canvas = Image.new("RGB", (max_w, total_h), (255, 255, 255))
        y = 0
        for im in images:
            x_off = (max_w - im.width) // 2
            canvas.paste(im, (x_off, y))
            y += im.height
        out = io.BytesIO()
        canvas.save(out, format="PNG")
        return out.getvalue()
    finally:
        for im in images:
            im.close()


def _composite_figure_png(page, fig_rect, cap_rect) -> bytes | None:
    """design/150 — separate body/caption clips within column band, vstack."""
    from sentence_reading.pdf.extract import _render_page_clip

    if fig_rect is None and cap_rect is None:
        return None

    x0, x1 = _composite_x_band(page, fig_rect, cap_rect)
    parts: list[tuple[float, object]] = []
    if fig_rect is not None:
        clamped = _clamp_rect_x(fig_rect, x0, x1)
        if clamped is not None:
            parts.append((float(clamped.y0), clamped))
    if cap_rect is not None:
        clamped = _clamp_rect_x(cap_rect, x0, x1)
        if clamped is not None:
            parts.append((float(clamped.y0), clamped))
    if not parts:
        return None

    parts.sort(key=lambda t: t[0])
    strips: list[bytes] = []
    for _y, clip in parts:
        png = _render_page_clip(page, clip)
        if png:
            strips.append(png)
    return _vstack_pngs(strips)


def azure_layout_enabled() -> bool:
    """Kill switch: ASR_AZURE_LAYOUT=0 → PyMuPDF-only extract."""
    v = (os.environ.get("ASR_AZURE_LAYOUT") or "1").strip().lower()
    return v not in ("0", "false", "off", "no")


def _timeout_s() -> float:
    raw = (os.environ.get("ASR_AZURE_LAYOUT_TIMEOUT_S") or "180").strip()
    try:
        return max(30.0, float(raw))
    except ValueError:
        return 180.0


def _polygon_to_rect(polygon: list[float] | None):
    import fitz

    if not polygon or len(polygon) < 8:
        return None
    xs = [float(polygon[i]) for i in range(0, len(polygon), 2)]
    ys = [float(polygon[i]) for i in range(1, len(polygon), 2)]
    return fitz.Rect(
        min(xs) * _INCH_TO_PT,
        min(ys) * _INCH_TO_PT,
        max(xs) * _INCH_TO_PT,
        max(ys) * _INCH_TO_PT,
    )


def _region_page_and_rect(bounding_regions) -> tuple[int | None, object | None]:
    if not bounding_regions:
        return None, None
    br = bounding_regions[0]
    page_num = int(getattr(br, "page_number", None) or 1)
    page_index = page_num - 1
    polygon = list(getattr(br, "polygon", None) or [])
    return page_index, _polygon_to_rect(polygon)


def _figure_caption_text(figure) -> str:
    cap = getattr(figure, "caption", None)
    if cap is None:
        return ""
    return (getattr(cap, "content", None) or "").strip()


def _azure_caption_body_like(rest: str, *, full: str = "") -> bool:
    """design/149 — reject Azure strings that slip past _is_caption_line."""
    if len(full) > _AZURE_CAPTION_MAX_CHARS:
        return True
    if not rest:
        return False
    if _AZURE_BODY_REST.match(rest):
        return True
    if rest.count(".") >= 2:
        return True
    if "respectively" in rest.lower():
        return True
    if _AZURE_PERCENT.search(rest):
        return True
    return False


def _accept_azure_figure_caption(text: str) -> bool:
    from sentence_reading.pdf.extract import (
        _CAPTION_LABEL,
        _is_caption_line,
        _normalize_caption,
    )

    raw = _normalize_caption(text)
    if not raw or not _is_caption_line(raw, fig_scheme=True, table=False):
        return False
    m = _CAPTION_LABEL.match(raw)
    if not m:
        return False
    rest = raw[m.end() :].lstrip(" \t.:;·\u2013\u2014-")
    return not _azure_caption_body_like(rest, full=raw)


def _figure_caption_placeholder(raw: str, page_index: int) -> str:
    from sentence_reading.pdf.extract import _CAPTION_LABEL, _normalize_caption

    s = _normalize_caption(raw)
    m = _CAPTION_LABEL.match(s) if s else None
    if m:
        return f"{m.group(1)} (p.{page_index + 1})"
    return f"Figure (p.{page_index + 1})"


def _caption_pair_score(fig_rect, cap_rect) -> int | None:
    """Return distance score for caption below or above figure; None if no match."""
    mid = (float(cap_rect.x0) + float(cap_rect.x1)) / 2.0
    if mid < float(fig_rect.x0) - 24 or mid > float(fig_rect.x1) + 24:
        return None
    gap_below = float(cap_rect.y0) - float(fig_rect.y1)
    if -8 <= gap_below <= _CAPTION_PAIR_BELOW_PT:
        return abs(int(gap_below * 100))
    gap_above = float(fig_rect.y0) - float(cap_rect.y1)
    if -8 <= gap_above <= _CAPTION_PAIR_ABOVE_PT:
        return abs(int(gap_above * 100))
    return None


def _match_fig_caption_with_rect(page, rect) -> tuple[str, object | None]:
    from sentence_reading.pdf.extract import _labeled_caption_hits

    if rect is None:
        return "", None
    best: tuple[str, object | None, int] = ("", None, 10**9)
    for _key, caption, cap_rect in _labeled_caption_hits(
        page, fig_scheme=True, table=False
    ):
        dist = _caption_pair_score(rect, cap_rect)
        if dist is not None and dist < best[2]:
            best = (caption, cap_rect, dist)
    return best[0], best[1]


def _find_cap_rect_for_caption(page, rect, caption: str) -> object | None:
    from sentence_reading.pdf.extract import _labeled_caption_hits, _normalize_caption

    want = _normalize_caption(caption)
    if not want or rect is None:
        return None
    for _key, cap, cap_rect in _labeled_caption_hits(
        page, fig_scheme=True, table=False
    ):
        if _normalize_caption(cap) != want:
            continue
        if _caption_pair_score(rect, cap_rect) is not None:
            return cap_rect
    return None


def resolve_figure_caption(
    page,
    fig_rect,
    azure_text: str,
    page_index: int,
) -> tuple[str, object | None]:
    """design/149 — Azure caption → validated text + optional caption rect."""
    from sentence_reading.pdf.extract import _normalize_caption

    azure_raw = _normalize_caption(azure_text)
    if azure_raw and _accept_azure_figure_caption(azure_raw):
        return azure_raw, _find_cap_rect_for_caption(page, fig_rect, azure_raw)

    matched, cap_rect = _match_fig_caption_with_rect(page, fig_rect)
    if matched:
        return matched, cap_rect

    if azure_raw:
        return _figure_caption_placeholder(azure_raw, page_index), None

    return "", None


def _match_fig_caption(page, rect) -> str:
    caption, _ = _match_fig_caption_with_rect(page, rect)
    return caption


def _match_table_caption(page, rect) -> str:
    from sentence_reading.pdf.extract import _labeled_caption_hits

    if rect is None:
        return ""
    best = ("", 10**9)
    for _key, caption, cap_rect in _labeled_caption_hits(
        page, fig_scheme=False, table=True
    ):
        mid = (float(cap_rect.x0) + float(cap_rect.x1)) / 2.0
        if mid < float(rect.x0) - 24 or mid > float(rect.x1) + 24:
            continue
        gap = float(rect.y0) - float(cap_rect.y1)
        if -8 <= gap <= 160:
            dist = abs(gap)
            if dist < best[1]:
                best = (caption, dist)
    return best[0]


def _read_figure_png(client, *, model_id: str, result_id: str, figure_id: str) -> bytes:
    resp = client.get_analyze_result_figure(
        model_id=model_id,
        result_id=result_id,
        figure_id=figure_id,
    )
    if isinstance(resp, (bytes, bytearray)):
        return bytes(resp)
    return b"".join(resp)


def extract_figures_azure(pdf_path: Path) -> list[Figure]:
    """Layout analyze with figure crops; tables clipped via PyMuPDF from Azure bboxes."""
    from sentence_reading.llm.env import (
        azure_document_intelligence_available,
        azure_document_intelligence_endpoint,
        azure_document_intelligence_key,
    )

    if not azure_document_intelligence_available():
        raise RuntimeError("azure_document_intelligence_not_configured")

    from azure.ai.documentintelligence import DocumentIntelligenceClient
    from azure.ai.documentintelligence.models import AnalyzeOutputOption
    from azure.core.credentials import AzureKeyCredential

    from sentence_reading.fig_refs import caption_key
    from sentence_reading.pdf.extract import _caption_sort_key, _png_data_url, _render_page_clip

    endpoint = azure_document_intelligence_endpoint() or ""
    key = azure_document_intelligence_key() or ""
    client = DocumentIntelligenceClient(
        endpoint=endpoint,
        credential=AzureKeyCredential(key),
    )

    import fitz

    doc = fitz.open(pdf_path)
    items: list[tuple[tuple, int, float, float, Figure]] = []
    try:
        with pdf_path.open("rb") as pdf_file:
            poller = client.begin_analyze_document(
                "prebuilt-layout",
                body=pdf_file,
                output=[AnalyzeOutputOption.FIGURES],
            )
        result = poller.result(timeout=_timeout_s())
        operation_id = str(poller.details.get("operation_id") or "")

        for figure in result.figures or []:
            fig_id = getattr(figure, "id", None)
            if not fig_id or not operation_id:
                continue
            page_index, rect = _region_page_and_rect(
                getattr(figure, "bounding_regions", None) or []
            )
            if page_index is None or page_index < 0 or page_index >= len(doc):
                continue

            page = doc[page_index]
            caption, cap_rect = resolve_figure_caption(
                page,
                rect,
                _figure_caption_text(figure),
                page_index,
            )

            azure_png = b""
            try:
                azure_png = _read_figure_png(
                    client,
                    model_id=result.model_id,
                    result_id=operation_id,
                    figure_id=str(fig_id),
                )
            except Exception as exc:
                log.warning("azure figure crop failed %s: %s", fig_id, exc)

            png = b""
            if rect is not None:
                png = _composite_figure_png(page, rect, cap_rect) or b""
            if not png:
                png = azure_png
            if not png and rect is not None:
                png = _render_page_clip(page, rect) or b""
            if not png:
                continue

            sort_y = float(rect.y0) if rect is not None else 0.0
            sort_x = float(rect.x0) if rect is not None else 0.0
            cap = caption or f"Figure (p.{page_index + 1})"
            items.append(
                (
                    _caption_sort_key(cap),
                    page_index,
                    sort_y,
                    sort_x,
                    Figure(
                        id="fig-azure",
                        image_src=_png_data_url(png),
                        caption=cap,
                        page_index=page_index,
                    ),
                )
            )

        for table in result.tables or []:
            page_index, rect = _region_page_and_rect(
                getattr(table, "bounding_regions", None) or []
            )
            if page_index is None or rect is None or page_index < 0 or page_index >= len(doc):
                continue
            page = doc[page_index]
            caption = _match_table_caption(page, rect)
            clip = rect
            if caption:
                from sentence_reading.pdf.extract import _labeled_caption_hits

                for _key, cap, cap_rect in _labeled_caption_hits(
                    page, fig_scheme=False, table=True
                ):
                    if cap == caption:
                        clip = rect | cap_rect
                        break
            png = _render_page_clip(page, clip)
            if not png:
                continue
            cap = caption or f"Table (p.{page_index + 1})"
            items.append(
                (
                    _caption_sort_key(cap),
                    page_index,
                    float(clip.y0),
                    float(clip.x0),
                    Figure(
                        id="tbl-azure",
                        image_src=_png_data_url(png),
                        caption=cap,
                        page_index=page_index,
                    ),
                )
            )

        items.sort(key=lambda t: (t[0], t[1], t[2], t[3]))
        seen: set[str] = set()
        out: list[Figure] = []
        for _sk, _pi, _y, _x, fig in items:
            key = caption_key(fig.caption) or f"raw:{fig.caption[:40]}"
            if key in seen:
                continue
            seen.add(key)
            out.append(fig)
            if len(out) >= 200:
                break
        return out
    finally:
        doc.close()
