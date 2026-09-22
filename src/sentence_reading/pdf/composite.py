"""
design/150/151 — column clamp + vstack composite and honest placeholders.

Moved from azure_layout.py so extract_figures_v2 and figure_edit share one path.
"""

from __future__ import annotations

import io
import re

_FULL_WIDTH_FRAC = 0.55


def _rect_spans_gutter(page_rect, rect) -> bool:
    """True when rect crosses page midpoint (full-width figure/caption)."""
    mid = (float(page_rect.x0) + float(page_rect.x1)) / 2.0
    x0, x1 = float(rect.x0), float(rect.x1)
    return x0 < mid - 2 and x1 > mid + 2


def composite_x_band(page, fig_rect, cap_rect) -> tuple[float, float]:
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


def clamp_rect_x(rect, x0: float, x1: float):
    """Intersect rect with column x band; preserve y."""
    import fitz

    r = fitz.Rect(rect)
    r.x0 = max(float(r.x0), x0)
    r.x1 = min(float(r.x1), x1)
    if r.x1 <= r.x0 + 1:
        return None
    return r


# design/361 — the area the single-strip side cap already implies (6400^2). Six stacked
# pages of Advanced Energy Materials' Table 1 come to 5960x22702 = 135 megapixels at the
# usual 8x zoom, which is not a phone image.
#
# The budget is spent by *rendering* smaller, not by shrinking the finished canvas.
# Resampling a table of 7pt type turns crisp glyph edges into grey ramps, and the PNG
# came out at 4.4 MB — larger than the 3.8 MB original it was meant to reduce.
VSTACK_MAX_PIXELS = 41_000_000


def zoom_for_area(rects, *, budget: int = VSTACK_MAX_PIXELS, full: float = 8.0) -> float:
    """The render zoom that keeps these clips inside the pixel budget together."""
    area = 0.0
    for r in rects:
        if r is None:
            continue
        area += max(float(r.x1) - float(r.x0), 1.0) * max(float(r.y1) - float(r.y0), 1.0)
    if area <= 0:
        return full
    return max(2.0, min(full, (budget / area) ** 0.5))


def vstack_pngs(strips: list[bytes], *, max_pixels: int | None = None) -> bytes | None:
    """Stack PNG byte strips vertically; equalize width on white canvas."""
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
        if len(images) == 1 and not max_pixels:
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
        if max_pixels and max_w * total_h > max_pixels:
            scale = (max_pixels / float(max_w * total_h)) ** 0.5
            shrunk = canvas.resize(
                (max(1, int(max_w * scale)), max(1, int(total_h * scale))),
                Image.LANCZOS,
            )
            canvas.close()
            canvas = shrunk
        out = io.BytesIO()
        canvas.save(out, format="PNG")
        canvas.close()
        return out.getvalue()
    finally:
        for im in images:
            im.close()


def composite_figure_png(page, fig_rect, cap_rect) -> bytes | None:
    """design/150 — separate body/caption clips within column band, vstack."""
    from sentence_reading.pdf.extract import _render_page_clip

    if fig_rect is None and cap_rect is None:
        return None

    x0, x1 = composite_x_band(page, fig_rect, cap_rect)
    parts: list[tuple[float, object]] = []
    if fig_rect is not None:
        clamped = clamp_rect_x(fig_rect, x0, x1)
        if clamped is not None:
            parts.append((float(clamped.y0), clamped))
    if cap_rect is not None:
        clamped = clamp_rect_x(cap_rect, x0, x1)
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
    return vstack_pngs(strips)


def composite_table_png(page, body_rect, cap_rect) -> bytes | None:
    """design/151 — table caption above body via y-sorted vstack."""
    import fitz

    from sentence_reading.pdf.extract import _render_page_clip

    if body_rect is None and cap_rect is None:
        return None

    body = fitz.Rect(body_rect) if body_rect is not None else None
    cap = fitz.Rect(cap_rect) if cap_rect is not None else None
    # WHY: symmetric 6pt clip pad on both strips inflates caption↔table gap; body
    # top pad also bleeds into caption band (ghost duplicate line).
    if body is not None and cap is not None and float(cap.y1) <= float(body.y0) + 24:
        body.y0 = max(float(body.y0), float(cap.y1) + 0.5)

    x0, x1 = composite_x_band(page, body, cap)
    _side = 6.0
    parts: list[tuple[float, object, str]] = []
    if cap is not None:
        clamped = clamp_rect_x(cap, x0, x1)
        if clamped is not None:
            parts.append((float(clamped.y0), clamped, "caption"))
    if body is not None:
        clamped = clamp_rect_x(body, x0, x1)
        if clamped is not None:
            parts.append((float(clamped.y0), clamped, "body"))
    if not parts:
        return None

    parts.sort(key=lambda t: t[0])
    strips: list[bytes] = []
    for _y, clip, role in parts:
        if role == "caption":
            cap_clip = fitz.Rect(clip)
            # Single-line table captions (~10pt Azure box + 6pt top pad) must not fail min height.
            if body is not None and cap_clip.height < 12:
                cap_clip.y1 = min(float(body.y0) - 0.5, float(cap_clip.y1) + 4)
            png = _render_page_clip(
                page,
                cap_clip,
                pad_top=_side,
                pad_left=_side,
                pad_right=_side,
                pad_bottom=0,
                min_height=8,
            )
        else:
            png = _render_page_clip(
                page,
                clip,
                pad_top=0,
                pad_left=_side,
                pad_right=_side,
                pad_bottom=_side,
            )
        if png:
            strips.append(png)
    return vstack_pngs(strips)


# design/361 — PIL's ROTATE_90 turns counter-clockwise, so a page whose baselines run
# up the sheet (`cw`) needs ROTATE_270 to come up the right way round.
_TURN_TO_PIL = {"cw": 270, "ccw": 90}


def rotate_png(png: bytes, turn: str) -> bytes:
    """Turn a rendered crop upright. Returns the input unchanged when turn is empty."""
    deg = _TURN_TO_PIL.get(turn or "")
    if not png or deg is None:
        return png
    from PIL import Image

    im = None
    try:
        im = Image.open(io.BytesIO(png)).convert("RGB")
        turned = im.rotate(deg, expand=True)
        out = io.BytesIO()
        turned.save(out, format="PNG")
        turned.close()
        return out.getvalue()
    except Exception:  # noqa: BLE001
        return png
    finally:
        if im is not None:
            im.close()


def composite_sideways_png(
    page, body_rect, cap_rect, turn: str, *, zoom: float | None = None
) -> bytes | None:
    """One clip over caption and body, then turned upright (design/361).

    The upright path clips caption and body separately and stacks them top to bottom.
    On a sideways page that order is wrong: Advanced Energy Materials prints Table 1's
    caption at `x 49..59` in the left margin and the table at `x 70..539`, so the
    caption is to the *left* of the table, not above it. Cutting both in one clip and
    turning it once puts the caption back on top without any rule about which side a
    caption takes — the page already laid it out, we only re-orient it.
    """
    import fitz

    from sentence_reading.pdf.extract import _render_page_clip

    rects = [r for r in (body_rect, cap_rect) if r is not None]
    if not rects:
        return None
    clip = fitz.Rect(rects[0])
    for r in rects[1:]:
        clip = clip | fitz.Rect(r)
    kwargs = {} if zoom is None else {"zoom": zoom}
    png = _render_page_clip(page, clip, **kwargs)
    if not png:
        return None
    return rotate_png(png, turn)


def placeholder_png(label: str, *, width: int = 480, height: int = 240) -> bytes:
    """design/124/151 — honest empty slot placeholder."""
    from PIL import Image, ImageDraw, ImageFont

    im = Image.new("RGB", (width, height), (245, 245, 245))
    draw = ImageDraw.Draw(im)
    text = (label or "missing").strip()
    try:
        font = ImageFont.load_default()
    except Exception:  # noqa: BLE001
        font = None
    draw.rectangle([8, 8, width - 8, height - 8], outline=(180, 180, 180), width=2)
    if font is not None:
        bbox = draw.textbbox((0, 0), text, font=font)
        tw = bbox[2] - bbox[0]
        th = bbox[3] - bbox[1]
        draw.text(((width - tw) // 2, (height - th) // 2), text, fill=(80, 80, 80), font=font)
    out = io.BytesIO()
    im.save(out, format="PNG")
    im.close()
    return out.getvalue()


def slot_kind_word(kind: str) -> str:
    """The word the paper printed for this kind (design/362)."""
    if kind == "table":
        return "Table"
    if kind == "scheme":
        return "Scheme"
    return "Figure"


def slot_missing_caption(kind: str, n: int) -> str:
    return f"{slot_kind_word(kind)} {n} (missing)"


def slot_unnumbered_caption(kind: str) -> str:
    """design/324 — a rescued body whose caption never parsed.

    It must not borrow the next integer: asserting `Figure 4` in a paper that
    prints three figures invents a label (design/124 — no success theatre).
    """
    if kind == "table":
        return "번호 없는 표"
    if kind == "scheme":
        return "번호 없는 반응식"
    return "번호 없는 그림"


def rect_from_dict(d: dict | None):
    import fitz

    if not isinstance(d, dict):
        return None
    try:
        return fitz.Rect(
            float(d["x0"]),
            float(d["y0"]),
            float(d["x1"]),
            float(d["y1"]),
        )
    except (KeyError, TypeError, ValueError):
        return None


def rect_to_dict(rect) -> dict:
    return {
        "x0": float(rect.x0),
        "y0": float(rect.y0),
        "x1": float(rect.x1),
        "y1": float(rect.y1),
    }


def parse_slot_n(key: str) -> int | None:
    m = re.match(r"^(?:fig|table|scheme):(\d+)", (key or "").lower())
    if not m:
        return None
    return int(m.group(1))
