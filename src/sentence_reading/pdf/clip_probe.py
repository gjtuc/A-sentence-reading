"""
design/323 — is a rendered figure crop cut off?

The only clipping signal that existed was `is_caption_only_figure_png`, a single
aspect-ratio heuristic (`height <= 400 and width > height*4`). A figure clipped
to 60% of its real extent passed every guard.

This measures ink instead of shape: find the bounding box of non-background
pixels and report which crop edges the ink touches. Ink flush against an edge
means the drawing continues past the crop. A figure with margins on all four
sides was almost certainly captured whole.

Pure and testable — no Azure, no network, no paper text.
"""

from __future__ import annotations

from dataclasses import dataclass

# A scanned/anti-aliased white is not 255. Treat near-white as background.
INK_THRESHOLD = 240
# Ink within this many pixels of a side counts as touching it.
EDGE_MARGIN_PX = 2
# Below this, an edge touch is more likely a border/frame than a cut.
MIN_EDGE_RUN_FRAC = 0.10


@dataclass(frozen=True)
class ClipReport:
    width: int
    height: int
    ink_x0: int
    ink_y0: int
    ink_x1: int
    ink_y1: int
    touches: tuple[str, ...]
    ink_frac: float
    blank: bool

    def to_dict(self) -> dict[str, object]:
        return {
            "width": self.width,
            "height": self.height,
            "ink_box": [self.ink_x0, self.ink_y0, self.ink_x1, self.ink_y1],
            "touches": list(self.touches),
            "touch_n": len(self.touches),
            "ink_frac": round(self.ink_frac, 4),
            "blank": self.blank,
        }


def _edge_runs(mask, width: int, height: int) -> dict[str, float]:
    """Fraction of each border line that carries ink."""
    px = mask.load()
    left = sum(1 for y in range(height) if any(
        px[x, y] for x in range(min(EDGE_MARGIN_PX + 1, width))
    ))
    right = sum(1 for y in range(height) if any(
        px[width - 1 - x, y] for x in range(min(EDGE_MARGIN_PX + 1, width))
    ))
    top = sum(1 for x in range(width) if any(
        px[x, y] for y in range(min(EDGE_MARGIN_PX + 1, height))
    ))
    bottom = sum(1 for x in range(width) if any(
        px[x, height - 1 - y] for y in range(min(EDGE_MARGIN_PX + 1, height))
    ))
    return {
        "left": left / max(1, height),
        "right": right / max(1, height),
        "top": top / max(1, width),
        "bottom": bottom / max(1, width),
    }


def clip_report(png_bytes: bytes) -> ClipReport | None:
    """Ink box + which edges it reaches. None when the PNG cannot be read."""
    if not png_bytes:
        return None
    import io

    from PIL import Image

    try:
        im = Image.open(io.BytesIO(png_bytes)).convert("L")
    except Exception:  # noqa: BLE001
        return None
    width, height = im.size
    if width <= 0 or height <= 0:
        return None

    mask = im.point(lambda v: 255 if v < INK_THRESHOLD else 0, mode="1")
    box = mask.getbbox()
    if box is None:
        return ClipReport(
            width=width,
            height=height,
            ink_x0=0,
            ink_y0=0,
            ink_x1=0,
            ink_y1=0,
            touches=(),
            ink_frac=0.0,
            blank=True,
        )
    x0, y0, x1, y1 = box
    runs = _edge_runs(mask, width, height)
    touches = tuple(
        side
        for side in ("left", "right", "top", "bottom")
        if runs[side] >= MIN_EDGE_RUN_FRAC
    )
    area = float(width * height)
    ink_frac = ((x1 - x0) * (y1 - y0)) / area if area else 0.0
    return ClipReport(
        width=width,
        height=height,
        ink_x0=x0,
        ink_y0=y0,
        ink_x1=x1,
        ink_y1=y1,
        touches=touches,
        ink_frac=ink_frac,
        blank=False,
    )


def clip_verdicts(reports: list[tuple[str, ClipReport | None]]) -> list[str]:
    """design/323 — name slots whose crop looks cut or empty."""
    out: list[str] = []
    blank = [k for k, r in reports if r is not None and r.blank]
    unreadable = [k for k, r in reports if r is None]
    # A figure cut on two or more sides is very unlikely to be framed art.
    cut = [k for k, r in reports if r is not None and not r.blank and len(r.touches) >= 2]
    if blank:
        out.append(f"figure_crop_blank:{len(blank)}")
    if unreadable:
        out.append(f"figure_crop_unreadable:{len(unreadable)}")
    if cut:
        out.append(f"figure_crop_edge_ink:{len(cut)}")
    return out
