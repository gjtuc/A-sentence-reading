"""
무엇을: PDF 바이트 → 그림·표 목록(+캡션) + 원문 텍스트.
왜: Fig/Table 은 본문과 위치가 어긋나므로 하단 캐러셀에 따로 둔다.
     그림 캡션은 아래, 표 캡션은 위에 있는 경우가 많다.
다음에: 다단 reading-order, 스캔본 OCR, Gemini 보조 매칭.
"""

from __future__ import annotations

import base64
import re
from pathlib import Path

from sentence_reading.models import Figure

# WHY: 로고·아이콘 대량 혼입 완화 (docs/design/02-pdf-extract.md)
_MIN_SIDE_PX = 40
_MIN_BYTES = 2_000
_CAPTION_BELOW_PT = 110.0
_CAPTION_ABOVE_PT = 90.0
_FIG_CAPTION_START = re.compile(
    r"^\s*((?:Fig(?:ure)?|Scheme)\.?\s*S?\d+[a-z]?)\b",
    re.IGNORECASE,
)
_TABLE_CAPTION_START = re.compile(
    r"^\s*(Table\.?\s*S?\d+[a-z]?)\b",
    re.IGNORECASE,
)


def _normalize_caption(text: str) -> str:
    t = re.sub(r"\s+", " ", (text or "").strip())
    return t[:900]


def _text_blocks(page) -> list[tuple[float, float, float, float, str]]:
    out: list[tuple[float, float, float, float, str]] = []
    try:
        blocks = page.get_text("blocks") or []
    except Exception:
        return out
    for block in blocks:
        if len(block) < 5 or not isinstance(block[4], str):
            continue
        x0, y0, x1, y1, text = block[0], block[1], block[2], block[3], block[4]
        out.append((float(x0), float(y0), float(x1), float(y1), text))
    return out


def _horiz_ok(bx0: float, bx1: float, rx0: float, rx1: float, mid: float) -> bool:
    overlap = min(bx1, rx1) - max(bx0, rx0)
    width = max(rx1 - rx0, 1.0)
    under_center = rx0 - 40 <= mid <= rx1 + 40
    return overlap >= 0.12 * width or under_center


def _caption_under_image(page, img_rect) -> str:
    """그림 바로 아래 Fig./Scheme 캡션."""
    hits: list[tuple[float, str]] = []
    for x0, y0, x1, y1, text in _text_blocks(page):
        if y0 < img_rect.y1 - 2:
            continue
        if y0 > img_rect.y1 + _CAPTION_BELOW_PT:
            continue
        mid = (x0 + x1) / 2
        if not _horiz_ok(x0, x1, img_rect.x0, img_rect.x1, mid):
            continue
        raw = text.strip()
        if not raw or not _FIG_CAPTION_START.match(raw):
            continue
        hits.append((y0, _normalize_caption(raw)))
    if not hits:
        return ""
    hits.sort(key=lambda t: t[0])
    return hits[0][1]


def _caption_above_table(page, table_rect) -> tuple[str, object | None]:
    """
    표 바로 위 Table N 캡션.
    Returns (caption_text, caption_rect_or_None).
    """
    import fitz

    hits: list[tuple[float, str, object]] = []
    for x0, y0, x1, y1, text in _text_blocks(page):
        if y1 > table_rect.y0 + 4:
            continue
        if y1 < table_rect.y0 - _CAPTION_ABOVE_PT:
            continue
        mid = (x0 + x1) / 2
        if not _horiz_ok(x0, x1, table_rect.x0, table_rect.x1, mid):
            continue
        raw = text.strip()
        if not raw or not _TABLE_CAPTION_START.match(raw):
            continue
        hits.append((y0, _normalize_caption(raw), fitz.Rect(x0, y0, x1, y1)))
    if not hits:
        return "", None
    # 표에 가장 가까운(아래쪽) 캡션
    hits.sort(key=lambda t: t[0], reverse=True)
    return hits[0][1], hits[0][2]


def _png_data_url(png: bytes) -> str:
    return "data:image/png;base64," + base64.b64encode(png).decode("ascii")


def _render_page_clip(page, rect, *, zoom: float = 2.0) -> bytes | None:
    """캡션+표/그림 영역을 페이지에서 잘라 PNG로."""
    import fitz

    page_rect = page.rect
    clip = fitz.Rect(rect)
    pad = 6
    clip.x0 = max(page_rect.x0, clip.x0 - pad)
    clip.y0 = max(page_rect.y0, clip.y0 - pad)
    clip.x1 = min(page_rect.x1, clip.x1 + pad)
    clip.y1 = min(page_rect.y1, clip.y1 + pad)
    if clip.width < 20 or clip.height < 20:
        return None
    try:
        pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), clip=clip, alpha=False)
        png = pix.tobytes("png")
    except Exception:
        return None
    if len(png) < _MIN_BYTES:
        return None
    return png


def _extract_embedded_images(page, page_index: int, start_i: int) -> list[tuple[float, Figure]]:
    """embedded 이미지 + 하단 Fig 캡션. (sort_y, Figure) 목록."""
    import fitz

    items: list[tuple[float, Figure]] = []
    seen_xref: set[int] = set()
    fig_i = start_i

    for img in page.get_images(full=True):
        xref = int(img[0])
        if xref in seen_xref:
            continue
        seen_xref.add(xref)

        try:
            rects = page.get_image_rects(xref) or []
        except Exception:
            rects = []
        img_rect = rects[0] if rects else None

        try:
            pix = fitz.Pixmap(page.parent, xref)
            if pix.n - pix.alpha >= 4:
                pix = fitz.Pixmap(fitz.csRGB, pix)
            elif pix.alpha:
                pix = fitz.Pixmap(fitz.csRGB, pix)
            if min(pix.width, pix.height) < _MIN_SIDE_PX:
                continue
            png = pix.tobytes("png")
        except Exception:
            continue

        if len(png) < _MIN_BYTES:
            continue

        caption = _caption_under_image(page, img_rect) if img_rect is not None else ""
        # WHY: 표지·Elsevier 로고 등 Fig/Scheme 캡션 없는 임베디드는 캐러셀에서 제외
        if not caption:
            continue

        # 캡션까지 포함해 페이지 클립 (전체화면에서 설명 잘 보이게)
        clip = fitz.Rect(img_rect)
        clip.y1 = min(page.rect.y1, img_rect.y1 + _CAPTION_BELOW_PT)
        rendered = _render_page_clip(page, clip)
        if rendered:
            png = rendered

        fig_i += 1
        y0 = float(img_rect.y0)
        items.append(
            (
                y0,
                Figure(
                    id=f"fig-{fig_i:04d}",
                    image_src=_png_data_url(png),
                    caption=caption,
                    page_index=page_index,
                ),
            )
        )
        if len(items) + start_i >= 200:
            break

    return items


def _extract_tables(page, page_index: int, start_i: int) -> list[tuple[float, Figure]]:
    """find_tables + 위쪽 Table 캡션을 한 장으로 렌더."""
    import fitz

    items: list[tuple[float, Figure]] = []
    fig_i = start_i
    try:
        finder = page.find_tables()
        tables = list(getattr(finder, "tables", None) or [])
    except Exception:
        tables = []

    used: list[object] = []

    for tab in tables:
        try:
            bbox = fitz.Rect(tab.bbox)
        except Exception:
            continue
        if bbox.width < 40 or bbox.height < 30:
            continue
        # 이미 잡은 표와 크게 겹치면 skip
        skip = False
        for prev in used:
            inter = bbox & prev
            if inter.get_area() > 0.5 * min(bbox.get_area(), prev.get_area()):
                skip = True
                break
        if skip:
            continue

        caption, cap_rect = _caption_above_table(page, bbox)
        clip = fitz.Rect(bbox)
        if cap_rect is not None:
            clip |= cap_rect
        else:
            # 캡션 텍스트를 못 찾으면 위쪽 여백만 조금 포함
            clip.y0 = max(page.rect.y0, clip.y0 - 28)

        png = _render_page_clip(page, clip, zoom=2.0)
        if not png:
            continue

        used.append(bbox)
        fig_i += 1
        if not caption:
            caption = f"Table (p.{page_index + 1})"
        items.append(
            (
                float(clip.y0),
                Figure(
                    id=f"tbl-{fig_i:04d}",
                    image_src=_png_data_url(png),
                    caption=caption,
                    page_index=page_index,
                ),
            )
        )
        if len(items) + start_i >= 200:
            break

    return items


def extract_figures(pdf_path: Path) -> list[Figure]:
    """
    그림(embedded) + 표(find_tables)를 페이지·세로 순으로 합친다.
    표는 캡션(위)과 표 본문을 한 PNG로 잘라 캐러셀에 넣는다.
    """
    import fitz

    doc = fitz.open(pdf_path)
    try:
        if doc.is_encrypted:
            raise ValueError("encrypted_pdf")

        ordered: list[tuple[int, float, Figure]] = []
        seq = 0

        for page_index, page in enumerate(doc):
            imgs = _extract_embedded_images(page, page_index, seq)
            seq += len(imgs)
            for y0, fig in imgs:
                ordered.append((page_index, y0, fig))

            tables = _extract_tables(page, page_index, seq)
            seq += len(tables)
            for y0, fig in tables:
                ordered.append((page_index, y0, fig))

            if len(ordered) >= 200:
                break

        ordered.sort(key=lambda t: (t[0], t[1]))
        # id 재부여 — 읽기 순서
        out: list[Figure] = []
        for i, (_, _, fig) in enumerate(ordered[:200], start=1):
            prefix = "tbl" if fig.id.startswith("tbl-") else "fig"
            out.append(
                Figure(
                    id=f"{prefix}-{i:04d}",
                    image_src=fig.image_src,
                    caption=fig.caption,
                    page_index=fig.page_index,
                )
            )
        return out
    finally:
        doc.close()


def _normalize_page_text(raw: str) -> str:
    raw = re.sub(r"(\w)-\n(\w)", r"\1\2", raw or "")
    raw = re.sub(r"(?<!\n)\n(?!\n)", " ", raw)
    raw = re.sub(r"[ \t]+", " ", raw)
    return raw.strip()


def extract_text_by_page(pdf_path: Path) -> list[str]:
    """페이지별 텍스트 (0-based). 단순 get_text — 다단 미보정."""
    import fitz

    doc = fitz.open(pdf_path)
    try:
        if doc.is_encrypted:
            raise ValueError("encrypted_pdf")
        return [_normalize_page_text(page.get_text("text") or "") for page in doc]
    finally:
        doc.close()


def join_page_texts(pages: list[str]) -> str:
    """페이지 텍스트를 본문 한 덩어리로."""
    return "\n\n".join(p for p in pages if (p or "").strip()).strip()


def extract_text(pdf_path: Path) -> str:
    """페이지 순서 텍스트. 1차는 단순 get_text (다단 미보정)."""
    return join_page_texts(extract_text_by_page(pdf_path))


def render_page_png(
    pdf_path: Path,
    page_index: int,
    *,
    dpi: float = 150.0,
    max_side_px: int = 1600,
) -> bytes:
    """
    페이지를 PNG 바이트로 렌더.
    WHY: Gemini vision OCR — 긴 변 max_side_px 로 비용·한도 완화.
    """
    import fitz

    doc = fitz.open(pdf_path)
    try:
        if doc.is_encrypted:
            raise ValueError("encrypted_pdf")
        if page_index < 0 or page_index >= doc.page_count:
            raise IndexError(f"page_index out of range: {page_index}")
        page = doc.load_page(page_index)
        zoom = dpi / 72.0
        mat = fitz.Matrix(zoom, zoom)
        pix = page.get_pixmap(matrix=mat, alpha=False)
        # 긴 변이 너무 크면 한 번 더 축소
        w, h = pix.width, pix.height
        long_side = max(w, h)
        if long_side > max_side_px and long_side > 0:
            scale = max_side_px / long_side
            mat2 = fitz.Matrix(zoom * scale, zoom * scale)
            pix = page.get_pixmap(matrix=mat2, alpha=False)
        return pix.tobytes("png")
    finally:
        doc.close()
