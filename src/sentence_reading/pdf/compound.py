"""
무엇을: 캡션 (a)(b)… 패널 수 → PNG 균등 크롭 → Fig. 1a/1b 목록.
왜: compound 통짜를 캐러셀에서 패널 단위로 (design/29). ML 분할 없음.
"""

from __future__ import annotations

import io
import re

from sentence_reading.models import Figure

_PANEL_MARK = re.compile(r"\(\s*([a-h])\s*\)", re.IGNORECASE)
_PANEL_RANGE = re.compile(
    r"\(\s*([a-h])\s*\)\s*(?:–|-|−|~|～)\s*\(\s*([a-h])\s*\)"
    r"|\(\s*([a-h])\s*(?:–|-|−|~|～)\s*([a-h])\s*\)",
    re.IGNORECASE,
)
_BASE_LABEL = re.compile(
    r"^\s*((?:Fig(?:ure)?|Scheme)\.?\s*(S?\d+))",
    re.IGNORECASE,
)
_MIN_PANEL_SIDE = 40


def _png_data_url(png: bytes) -> str:
    import base64

    return "data:image/png;base64," + base64.b64encode(png).decode("ascii")


def detect_panel_letters(caption: str) -> list[str]:
    """
    캡션에서 패널 글자 a,b,… (소문자 · 등장/범위 순).
    단일 (a)만 있으면 [] — 분해하지 않음.
    """
    text = caption or ""
    letters: list[str] = []
    seen: set[str] = set()

    rm = _PANEL_RANGE.search(text)
    if rm:
        a = (rm.group(1) or rm.group(3) or "").lower()
        b = (rm.group(2) or rm.group(4) or "").lower()
        if a and b:
            if a <= b:
                letters = [chr(c) for c in range(ord(a), ord(b) + 1)]
            else:
                letters = [chr(c) for c in range(ord(b), ord(a) + 1)]
            return letters if len(letters) >= 2 else []

    for m in _PANEL_MARK.finditer(text):
        ch = m.group(1).lower()
        if ch in seen:
            continue
        seen.add(ch)
        letters.append(ch)

    if len(letters) < 2:
        return []
    # WHY: a,c 만 있고 b 없으면 비연속 — 그래도 표시된 것만 크롭 칸 수로 씀
    return letters


def base_figure_label(caption: str) -> str:
    """Fig. 1 / Scheme 2 선두. 없으면 Fig."""
    m = _BASE_LABEL.match(caption or "")
    if m:
        raw = m.group(1)
        return re.sub(r"\s+", " ", raw.strip())
    return "Fig."


def panel_caption(base: str, letter: str, parent_caption: str) -> str:
    """Fig. 1a — (부모 캡션에서 패널 표시를 뺀 짧은 꼬리)."""
    letter = (letter or "a").lower()
    b = (base or "Fig.").rstrip(".")
    if re.search(r"\d$", b):
        head = f"{b}{letter}"
    else:
        head = f"{b} {letter}"
    tail = re.sub(r"\s+", " ", (parent_caption or "").strip())
    rest = _BASE_LABEL.sub("", tail, count=1).strip(" .:—–-")
    rest = _PANEL_RANGE.sub("", rest)
    rest = _PANEL_MARK.sub("", rest)
    rest = re.sub(r"\s+", " ", rest).strip(" .,—–-")[:120]
    if rest:
        return f"{head} — {rest}"[:900]
    return head[:900]


def choose_grid(n: int, width: int, height: int) -> tuple[int, int]:
    """(rows, cols) for n panels."""
    if n <= 1:
        return 1, 1
    wide = width >= height
    if n == 2:
        return (1, 2) if wide else (2, 1)
    if n == 3:
        return (1, 3) if width >= height * 1.15 else (3, 1)
    if n == 4:
        return 2, 2
    if n == 6:
        return (2, 3) if wide else (3, 2)
    if n == 8:
        return (2, 4) if wide else (4, 2)
    # 그 외: 가로 우선 한 줄, 너무 좁으면 세로
    if wide or width * 2 >= height * n:
        return 1, n
    return n, 1


def split_png_equal(png: bytes, rows: int, cols: int) -> list[bytes]:
    """균등 그리드 크롭. 실패·너무 작으면 []."""
    if not png or rows < 1 or cols < 1:
        return []
    try:
        from PIL import Image
    except ImportError:
        return []
    try:
        im = Image.open(io.BytesIO(png)).convert("RGB")
    except Exception:
        return []
    w, h = im.size
    if w < _MIN_PANEL_SIDE or h < _MIN_PANEL_SIDE:
        return []
    cell_w = w // cols
    cell_h = h // rows
    if cell_w < _MIN_PANEL_SIDE or cell_h < _MIN_PANEL_SIDE:
        return []
    out: list[bytes] = []
    for r in range(rows):
        for c in range(cols):
            left = c * cell_w
            upper = r * cell_h
            right = w if c == cols - 1 else (c + 1) * cell_w
            lower = h if r == rows - 1 else (r + 1) * cell_h
            crop = im.crop((left, upper, right, lower))
            buf = io.BytesIO()
            crop.save(buf, format="PNG", optimize=True)
            data = buf.getvalue()
            if len(data) < 50:
                return []
            out.append(data)
    return out


def expand_compound_png(
    png: bytes,
    caption: str,
    *,
    page_index: int | None,
    id_prefix: str,
    start_i: int,
) -> list[Figure] | None:
    """
    패널 분해 성공 시 Figure 목록, 아니면 None (호출측이 통짜 유지).
    """
    letters = detect_panel_letters(caption)
    if len(letters) < 2:
        return None
    n = len(letters)
    try:
        from PIL import Image

        im = Image.open(io.BytesIO(png))
        w, h = im.size
    except Exception:
        return None
    rows, cols = choose_grid(n, w, h)
    if rows * cols < n:
        return None
    parts = split_png_equal(png, rows, cols)
    if len(parts) < n:
        return None
    base = base_figure_label(caption)
    figures: list[Figure] = []
    for i, letter in enumerate(letters):
        figures.append(
            Figure(
                id=f"{id_prefix}-{start_i + i:04d}",
                image_src=_png_data_url(parts[i]),
                caption=panel_caption(base, letter, caption),
                page_index=page_index,
            )
        )
    return figures


def expand_compound_from_figure(
    fig: Figure,
    png: bytes,
    *,
    id_prefix: str = "fig",
    start_i: int = 1,
) -> list[Figure] | None:
    return expand_compound_png(
        png,
        fig.caption,
        page_index=fig.page_index,
        id_prefix=id_prefix,
        start_i=start_i,
    )
