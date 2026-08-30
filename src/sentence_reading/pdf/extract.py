"""
무엇을: PDF 바이트 → 그림·표 목록(+캡션) + 원문 텍스트.
왜: Fig/Table 은 본문과 위치가 어긋나므로 하단 캐러셀에 따로 둔다.
     그림 캡션은 아래, 표 캡션은 위에 있는 경우가 많다.
다음에: 스캔본 OCR 보강. reading-order → pdf/reading_order.py.
# NOTE: compound 자동 분리는 design/44 에서 extract 파이프라인 끊김 (모듈은 보관).
"""

from __future__ import annotations

import base64
import os
import re
from pathlib import Path

from sentence_reading.models import Figure

# WHY: 로고·아이콘 대량 혼입 완화 (docs/design/02-pdf-extract.md)
_MIN_SIDE_PX = 40
_MIN_BYTES = 2_000
# WHY: 크롭 확대 화질 — 페이지 클립 래스터 배율 (72dpi×8 ≈ 576dpi). 영역(clip)은 그대로.
_FIGURE_CLIP_ZOOM = 8.0
# WHY: 전면 그림 8× 시 OOM 완화. 긴 변만 줄이고 clip 범위는 유지.
_FIGURE_CLIP_MAX_SIDE_PX = 6400
_CAPTION_BELOW_PT = 110.0
_CAPTION_ABOVE_PT = 90.0
# design/125 — slightly wider pairing window (side-by-side / tall panels).
_CAPTION_PAIR_BELOW_PT = 150.0
_CAPTION_PAIR_ABOVE_PT = 120.0
# Orphan caption (no embed): clip this much above the caption line (vector/drawing).
_ORPHAN_CLIP_ABOVE_PT = 280.0
# design/125 — punct after number (Fig. 1. / Figure 2:).
_FIG_CAPTION_LINE = re.compile(
    r"^\s*((?:Fig(?:ure)?|Scheme)\.?\s*S?\d+[a-z]?)\s*[.:;·\u2013\u2014\-]",
    re.IGNORECASE,
)
_TABLE_CAPTION_LINE = re.compile(
    r"^\s*(Table\.?\s*S?\d+[a-z]?)\s*[.:;·\u2013\u2014\-]",
    re.IGNORECASE,
)
# design/126 — label + optional punct OR title-like remainder (not body verb).
_CAPTION_LABEL = re.compile(
    r"^\s*((?:Fig(?:ure)?|Scheme|Table)\.?\s*S?\d+[a-z]?)(?=$|[\s.:;·\u2013\u2014\-])",
    re.IGNORECASE,
)
# EDGE: body "Figure 4 illustrates…" — lowercase continuation after the number.
_BODY_AFTER_LABEL = re.compile(
    r"^(illustrates?|shows?|presents?|demonstrates?|depicts?|indicates?|"
    r"describes?|summarizes?|compares?|reports?|displays?|represents?|"
    r"is\b|are\b|was\b|were\b|has\b|have\b|can\b|will\b|may\b|must\b)",
    re.IGNORECASE,
)
# Legacy start-only (image-under pairing still accepts Scheme without punct).
_FIG_CAPTION_START = re.compile(
    r"^\s*((?:Fig(?:ure)?|Scheme)\.?\s*S?\d+[a-z]?)\b",
    re.IGNORECASE,
)
_TABLE_CAPTION_START = re.compile(
    r"^\s*(Table\.?\s*S?\d+[a-z]?)\b",
    re.IGNORECASE,
)
# design/92 — 캐러셀 정렬용 캡션 키 (Fig → Scheme → Table, 번호·문자)
_CAPTION_SORT_RE = re.compile(
    r"^\s*(Fig(?:ure)?|Scheme|Table)\.?\s*(S?)(\d+)([a-z])?\b",
    re.IGNORECASE,
)
_ABSTRACT_WORD = re.compile(r"\babstract\b", re.IGNORECASE)
# 초록 옆 graphical abstract: 앞쪽 페이지·큰 면적만 (로고 완화)
_GA_MAX_PAGE_INDEX = 1
_GA_MIN_AREA_PT2 = 12_000.0
_GA_MIN_SIDE_PT = 80.0
_RECT_OVERLAP_FRAC = 0.55

# design/135 — title-page cover as carousel slot 0 (fail-closed when unsure).
_COVER_CLIP_ZOOM = 2.5  # full-page; lower than fig zoom to bound PNG size/cost
_COVER_DOI = re.compile(r"\b10\.\d{4,9}/[-._;()/:A-Z0-9]+\b", re.IGNORECASE)
_COVER_AFFIL = re.compile(
    r"\b(University|Universit[aà]|Department|Institute|Laboratory|College|"
    r"School of|Centre|Center for|Academy of)\b",
    re.IGNORECASE,
)
_COVER_CORRESP = re.compile(
    r"\b(Corresponding\s+author|E-?mails?|Authors?\s+for\s+correspondence)\b",
    re.IGNORECASE,
)
_COVER_DATE_LINE = re.compile(
    r"\b(Received|Accepted|Published|Available\s+online)\b",
    re.IGNORECASE,
)
_COVER_COPYRIGHT = re.compile(r"(©|\([Cc]\)|Copyright)\s*\d{4}", re.IGNORECASE)
_COVER_BODY_HEAD = re.compile(
    r"^\s*(\d+\.?\s*)?(Introduction|Experimental|Results and discussion|"
    r"Results|Methods|Materials and methods|References)\b",
    re.IGNORECASE | re.MULTILINE,
)
# "Jane A. Doe," / "Jane Doe1," — weak author-line hint (not unique alone).
_COVER_AUTHOR_LINE = re.compile(
    r"^[A-ZÀ-ÖØ-Þ][A-Za-zÀ-ÖØ-öø-ÿ''\-]{1,40}"
    r"(?:\s+[A-Z]\.){0,3}"
    r"(?:\s+[A-ZÀ-ÖØ-Þ][A-Za-zÀ-ÖØ-öø-ÿ''\-]{1,40}){1,4}"
    r"(?:\s*[,，]|\s*\d|\s*$)",
)
_COVER_CAPTION = "Title page (p.1)"


def cover_as_figure_enabled() -> bool:
    """Kill switch: ASR_COVER_AS_FIGURE=0 skips title-page cover slot."""
    import os

    v = (os.environ.get("ASR_COVER_AS_FIGURE") or "1").strip().lower()
    return v not in ("0", "false", "off", "no")


def page_text_looks_like_title_cover(text: str) -> bool:
    """Heuristic (design/135 B): title/author-like first page → True.

    Fail-closed: ambiguous or body-like text returns False (no fake cover).
    """
    raw = (text or "").replace("\x00", "").strip()
    if len(raw) < 40:
        return False

    # EDGE: page opens like a mid-paper section → never invent a cover.
    head = raw[:400]
    if _COVER_BODY_HEAD.search(head):
        # Allow only when strong front-matter signals still dominate.
        strong = 0
        if _COVER_DOI.search(raw):
            strong += 1
        if _COVER_CORRESP.search(raw):
            strong += 1
        if _COVER_AFFIL.search(raw):
            strong += 1
        if strong < 2:
            return False

    score = 0
    if _COVER_DOI.search(raw):
        score += 2
    if _COVER_CORRESP.search(raw) or ("@" in raw and _COVER_AFFIL.search(raw)):
        score += 2
    if _COVER_AFFIL.search(raw):
        score += 1
    if _COVER_DATE_LINE.search(raw):
        score += 1
    if _COVER_COPYRIGHT.search(raw):
        score += 1

    lines = [ln.strip() for ln in raw.splitlines() if ln.strip()]
    authorish = sum(1 for ln in lines[:40] if _COVER_AUTHOR_LINE.match(ln) and len(ln) < 120)
    if authorish >= 2:
        score += 2
    elif authorish == 1:
        score += 1

    # Title-ish: early long line that is not Abstract / Fig caption / body verb.
    for ln in lines[:12]:
        if len(ln) < 25 or len(ln) > 220:
            continue
        low = ln.lower()
        if low.startswith("abstract") or low.startswith("keywords"):
            continue
        if _CAPTION_LABEL.match(ln) or _COVER_BODY_HEAD.match(ln):
            continue
        if _COVER_AUTHOR_LINE.match(ln) and len(ln) < 80:
            continue
        # Prefer lines with mixed case / many capitals (titles), not plain body.
        letters = [c for c in ln if c.isalpha()]
        if len(letters) < 20:
            continue
        upper_frac = sum(1 for c in letters if c.isupper()) / len(letters)
        if upper_frac >= 0.12:
            score += 1
            break

    # WHY: need at least two weak signals or one strong (+2) pair — avoid logos-only.
    return score >= 2


def _maybe_title_cover_figure(doc) -> Figure | None:
    """Render page 0 as cover figure when heuristic passes; else None."""
    if not cover_as_figure_enabled():
        return None
    if doc is None or len(doc) < 1:
        return None
    page = doc[0]
    try:
        text = page.get_text("text") or ""
    except Exception:
        return None
    if not page_text_looks_like_title_cover(text):
        return None
    # Full-page clip; zoom bounded so Cloud Run memory stays sane.
    png = _render_page_clip(page, page.rect, zoom=_COVER_CLIP_ZOOM)
    if not png:
        return None
    return Figure(
        id="cov-0001",
        image_src=_png_data_url(png),
        caption=_COVER_CAPTION,
        page_index=0,
        slot_key="title_page:1",
    )


# design/131 — silent hard-cut for absurd OCR blobs only (never insert "…").
# Typical journal captions are << this; old 900 truncated long compound titles.
_CAPTION_MAX_CHARS = 8_000


def _normalize_caption(text: str) -> str:
    """Collapse whitespace; keep full caption up to safety ceiling.

    WHY raise past 900 (design/131): product wants full caption text stored and
    shown. EDGE: null/empty → ""; never append ellipsis (UI must not invent cuts).
    """
    t = re.sub(r"\s+", " ", (text or "").replace("\x00", "").strip())
    if len(t) > _CAPTION_MAX_CHARS:
        return t[:_CAPTION_MAX_CHARS]
    return t


def _is_caption_line(s: str, *, fig_scheme: bool, table: bool) -> bool:
    """
    design/126 — accept punct captions and title-like soft captions.
    Reject body sentences: ``Figure 4 illustrates…``.
    """
    raw = (s or "").strip()
    if not raw:
        return False
    m = _CAPTION_LABEL.match(raw)
    if not m:
        return False
    label = m.group(1)
    kind = label.lower()
    if fig_scheme and kind.startswith("table"):
        return False
    if table and not kind.startswith("table"):
        return False
    # Strict punct form always OK.
    if fig_scheme and _FIG_CAPTION_LINE.match(raw):
        return True
    if table and _TABLE_CAPTION_LINE.match(raw):
        return True
    rest = raw[m.end() :].lstrip(" \t.:;·\u2013\u2014-")
    if not rest:
        return True
    # Soft: next token looks like a caption title, not a body verb.
    if _BODY_AFTER_LABEL.match(rest):
        return False
    # Title-like: capital / digit / panel marker / non-Latin (common in KO/chem).
    ch0 = rest[0]
    if ch0.isupper() or ch0.isdigit() or ch0 in "([":
        return True
    # Lowercase Latin start without body-verb still risky — only allow Scheme/Table
    # short tails that are clearly panel letters handled above.
    if not ("a" <= ch0.lower() <= "z"):
        return True
    return False


def _slot_sort_key(slot_key: str) -> tuple[int, int]:
    """fig:3 → (0, 3); table:2 → (1, 2) — slot plan carousel order."""
    raw = (slot_key or "").strip().lower()
    m = re.match(r"^(fig|table):(\d+)$", raw)
    if not m:
        return (2, 10**9)
    kind_ord = 1 if m.group(1) == "table" else 0
    return (kind_ord, int(m.group(2)))


def _caption_sort_key(caption: str) -> tuple:
    """
    캡션 번호 순 정렬 키 (design/92).
    종류: Fig/Figure=0, Scheme=1, Table=2, 기타(GA·플레이스홀더)=3.
    S-번호(보충)는 본 번호 뒤(1).
    """
    raw = (caption or "").strip()
    m = _CAPTION_SORT_RE.match(raw)
    if not m:
        # design/135 — title cover before GA / numbered figs
        if raw.lower().startswith("title page"):
            return (-2, 0, 0, "")
        # Graphical abstract 등 — 본 Fig보다 앞(TOC)에 두되 번호군 밖
        if raw.lower().startswith("graphical abstract"):
            return (-1, 0, 0, "")
        return (3, 0, 10**9, "")
    kind = m.group(1).lower()
    if kind.startswith("fig"):
        kind_ord = 0
    elif kind.startswith("scheme"):
        kind_ord = 1
    else:
        kind_ord = 2
    supp = 1 if m.group(2) else 0
    num = int(m.group(3))
    letter = (m.group(4) or "").lower()
    return (kind_ord, supp, num, letter)


def _rects_heavily_overlap(a, b) -> bool:
    try:
        inter = a & b
        return inter.get_area() > _RECT_OVERLAP_FRAC * min(a.get_area(), b.get_area())
    except Exception:
        return False


def _page_has_abstract_near(page, img_rect) -> bool:
    """이미지와 같은 페이지에서 Abstract 라벨이 가로·세로로 가깝게 있는지."""
    for x0, y0, x1, y1, text in _text_blocks(page):
        if not _ABSTRACT_WORD.search(text or ""):
            continue
        # 세로: 이미지와 같은 밴드(위·옆·약간 아래)
        if y1 < img_rect.y0 - 80 or y0 > img_rect.y1 + 40:
            continue
        # 가로: 옆이거나 겹침
        mid = (x0 + x1) / 2
        if _horiz_ok(x0, x1, img_rect.x0, img_rect.x1, mid):
            return True
        gap = max(0.0, max(img_rect.x0 - x1, x0 - img_rect.x1))
        if gap < 120:
            return True
    return False


def _is_graphical_abstract_candidate(page, page_index: int, img_rect) -> bool:
    """캡션 없는 큰 임베디드가 초록 옆 TOC/GA 인지 (design/92)."""
    if page_index > _GA_MAX_PAGE_INDEX:
        return False
    if img_rect is None:
        return False
    if min(img_rect.width, img_rect.height) < _GA_MIN_SIDE_PT:
        return False
    if img_rect.get_area() < _GA_MIN_AREA_PT2:
        return False
    # 페이지 상단 헤더 로고 완화: 맨 위 8% 밴드는 제외
    if img_rect.y1 < page.rect.y0 + 0.08 * page.rect.height:
        return False
    return _page_has_abstract_near(page, img_rect)


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


# design/127 — label-only crumb left when Elsevier splits "Fig." from "3. Title".
_CAPTION_LABEL_ONLY = re.compile(
    r"^\s*(Fig(?:ure)?|Scheme|Table)\.?\s*$",
    re.IGNORECASE,
)
_CAPTION_NUM_START = re.compile(r"^\s*S?\d+[a-z]?\b", re.IGNORECASE)
# Mid-line caption only when not preceded by a letter (rejects ``in Fig. 3``).
# Two-column bleed is handled by x-gap splits in ``_page_caption_lines``.
_CAPTION_INLINE_START = re.compile(
    r"(?i)(?:^|(?<![A-Za-z])\s+)((?:Fig(?:ure)?|Scheme|Table)\.?\s*S?\d+[a-z]?\b.*)$"
)


def _page_caption_lines(page) -> list[tuple[str, object]]:
    """
    design/127 — rebuild reading lines from words (Elsevier word-per-newline).
    Returns (line_text, line_rect). Same-y words are split on large x-gaps
    (two-column bleed). Nearby crumbs like ``Fig.`` + ``4. Title`` are merged.
    """
    import fitz

    try:
        words = page.get_text("words") or []
    except Exception:
        words = []
    if not words:
        out: list[tuple[str, object]] = []
        for x0, y0, x1, y1, text in _text_blocks(page):
            joined = _normalize_caption(text)
            if joined:
                out.append((joined, fitz.Rect(x0, y0, x1, y1)))
        return _merge_label_num_crumbs(out)

    buckets: dict[int, list[tuple[float, float, float, float, str]]] = {}
    for w in words:
        if len(w) < 5:
            continue
        x0, y0, x1, y1, token = (
            float(w[0]),
            float(w[1]),
            float(w[2]),
            float(w[3]),
            str(w[4] or ""),
        )
        if not token.strip():
            continue
        key = int(round(y0 / 2.0) * 2)
        buckets.setdefault(key, []).append((x0, y0, x1, y1, token))

    lines: list[tuple[str, object]] = []
    gap_pt = 14.0
    for key in sorted(buckets):
        parts = sorted(buckets[key], key=lambda t: t[0])
        run: list[tuple[float, float, float, float, str]] = [parts[0]]
        for p in parts[1:]:
            prev = run[-1]
            if p[0] - prev[2] > gap_pt:
                text = _normalize_caption(" ".join(t[4] for t in run))
                if text:
                    x0 = min(t[0] for t in run)
                    y0 = min(t[1] for t in run)
                    x1 = max(t[2] for t in run)
                    y1 = max(t[3] for t in run)
                    lines.append((text, fitz.Rect(x0, y0, x1, y1)))
                run = [p]
            else:
                run.append(p)
        text = _normalize_caption(" ".join(t[4] for t in run))
        if text:
            x0 = min(t[0] for t in run)
            y0 = min(t[1] for t in run)
            x1 = max(t[2] for t in run)
            y1 = max(t[3] for t in run)
            lines.append((text, fitz.Rect(x0, y0, x1, y1)))
    return _merge_label_num_crumbs(lines)


def _merge_label_num_crumbs(
    lines: list[tuple[str, object]],
) -> list[tuple[str, object]]:
    """Join ``Fig.`` + ``4. Title…`` when they sit on the same baseline band."""
    import fitz

    if not lines:
        return lines
    out: list[tuple[str, object]] = []
    i = 0
    while i < len(lines):
        text, rect = lines[i]
        if _CAPTION_LABEL_ONLY.match(text) and i + 1 < len(lines):
            nxt, nrect = lines[i + 1]
            same_band = abs(float(rect.y0) - float(nrect.y0)) <= 4.0
            if same_band and _CAPTION_NUM_START.match(nxt):
                merged = _normalize_caption(f"{text} {nxt}")
                union = fitz.Rect(rect) | fitz.Rect(nrect)
                out.append((merged, union))
                i += 2
                continue
        out.append((text, rect))
        i += 1
    return out


def _horiz_ok(bx0: float, bx1: float, rx0: float, rx1: float, mid: float) -> bool:
    overlap = min(bx1, rx1) - max(bx0, rx0)
    width = max(rx1 - rx0, 1.0)
    under_center = rx0 - 40 <= mid <= rx1 + 40
    return overlap >= 0.12 * width or under_center


def _caption_under_image(page, img_rect) -> str:
    """그림 바로 아래 Fig./Scheme 캡션 (legacy helper · design/125 still used in GA path)."""
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
        # design/126 — soft caption OR punct; body verbs rejected inside helper.
        if not _is_caption_line(raw, fig_scheme=True, table=False):
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
        if not _is_caption_line(raw, fig_scheme=False, table=True):
            continue
        hits.append((y0, _normalize_caption(raw), fitz.Rect(x0, y0, x1, y1)))
    if not hits:
        return "", None
    # 표에 가장 가까운(아래쪽) 캡션
    hits.sort(key=lambda t: t[0], reverse=True)
    return hits[0][1], hits[0][2]


def _png_data_url(png: bytes) -> str:
    return "data:image/png;base64," + base64.b64encode(png).decode("ascii")


def _render_page_clip(
    page,
    rect,
    *,
    zoom: float = _FIGURE_CLIP_ZOOM,
    pad: float = 6,
    pad_top: float | None = None,
    pad_right: float | None = None,
    pad_bottom: float | None = None,
    pad_left: float | None = None,
    min_width: float = 20,
    min_height: float = 20,
) -> bytes | None:
    """캡션+표/그림 영역을 페이지에서 잘라 PNG로. zoom↑ = 같은 영역을 더 촘촘히 찍음."""
    import fitz

    page_rect = page.rect
    clip = fitz.Rect(rect)
    pt = pad if pad_top is None else pad_top
    pr = pad if pad_right is None else pad_right
    pb = pad if pad_bottom is None else pad_bottom
    pl = pad if pad_left is None else pad_left
    clip.x0 = max(page_rect.x0, clip.x0 - pl)
    clip.y0 = max(page_rect.y0, clip.y0 - pt)
    clip.x1 = min(page_rect.x1, clip.x1 + pr)
    clip.y1 = min(page_rect.y1, clip.y1 + pb)
    if clip.width < min_width or clip.height < min_height:
        return None
    try:
        pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), clip=clip, alpha=False)
        long_side = max(pix.width, pix.height)
        if long_side > _FIGURE_CLIP_MAX_SIDE_PX and long_side > 0:
            scale = _FIGURE_CLIP_MAX_SIDE_PX / long_side
            pix = page.get_pixmap(
                matrix=fitz.Matrix(zoom * scale, zoom * scale),
                clip=clip,
                alpha=False,
            )
        png = pix.tobytes("png")
    except Exception:
        return None
    if len(png) < _MIN_BYTES:
        return None
    return png


def _labeled_caption_hits(
    page, *, fig_scheme: bool, table: bool
) -> list[tuple[str, str, object]]:
    """
    design/125–127 — scan rebuilt text lines for Fig/Scheme/Table captions
    (word-join · punct/soft · body verbs rejected).
    design/137 — multiple labels on one line → separate hits.
    Returns list of (caption_key, caption_text, caption_rect).
    """
    from sentence_reading.fig_refs import caption_key
    from sentence_reading.pdf.caption_lumps import (
        maybe_fail_ambiguous_line,
        split_line_caption_segments,
    )

    def _is_cap_line(s: str) -> bool:
        return _is_caption_line(s, fig_scheme=fig_scheme, table=table)

    hits: list[tuple[str, str, object]] = []
    lines = _page_caption_lines(page)
    li = 0
    while li < len(lines):
        s, line_rect = lines[li]
        if not s:
            li += 1
            continue

        segments = split_line_caption_segments(s)
        valid_heads: list[tuple[int, str]] = []
        for idx, seg in enumerate(segments):
            if seg and _is_cap_line(seg):
                valid_heads.append((idx, seg))

        if not valid_heads:
            li += 1
            continue

        maybe_fail_ambiguous_line(s, valid_heads, is_caption_line=_is_cap_line)

        next_li = li + 1
        for vhi, (_seg_idx, head) in enumerate(valid_heads):
            parts = [head]
            union = line_rect
            j = li + 1
            is_last_on_line = vhi == len(valid_heads) - 1
            if is_last_on_line:
                while j < len(lines):
                    nxt, nrect = lines[j]
                    nxt_segs = split_line_caption_segments(nxt or "")
                    if any(ns and _is_cap_line(ns) for ns in nxt_segs):
                        break
                    if float(nrect.y0) > float(line_rect.y1) + 28:
                        break
                    parts.append(nxt)
                    union = union | nrect
                    j += 1
                next_li = j

            cap = _normalize_caption(" ".join(parts))
            key = caption_key(cap)
            if key:
                if fig_scheme and key.startswith("table:"):
                    continue
                if table and not key.startswith("table:"):
                    continue
                hits.append((key, cap, union))

        li = next_li
    return hits


def _list_embedded_rects(
    page,
) -> list[tuple[object, bytes]]:
    """(img_rect, base_png) for embeds that pass size filters."""
    import fitz

    out: list[tuple[object, bytes]] = []
    seen_xref: set[int] = set()
    for img in page.get_images(full=True):
        xref = int(img[0])
        if xref in seen_xref:
            continue
        seen_xref.add(xref)
        try:
            rects = list(page.get_image_rects(xref) or [])
        except Exception:
            rects = []
        if not rects:
            continue
        try:
            pix = fitz.Pixmap(page.parent, xref)
            if pix.n - pix.alpha >= 4:
                pix = fitz.Pixmap(fitz.csRGB, pix)
            elif pix.alpha:
                pix = fitz.Pixmap(fitz.csRGB, pix)
            if min(pix.width, pix.height) < _MIN_SIDE_PX:
                continue
            base_png = pix.tobytes("png")
        except Exception:
            continue
        if len(base_png) < _MIN_BYTES:
            continue
        for img_rect in rects:
            out.append((img_rect, base_png))
    return out


def _pick_embed_for_caption(
    cap_rect, embeds: list[tuple[object, bytes]], used: list[object]
) -> tuple[object, bytes, str] | None:
    """
    Match caption to nearest embed.
    Prefer image *above* caption (usual Fig layout); else image *below* (caption above).
    """
    candidates: list[tuple[tuple, object, bytes, str]] = []
    for img_rect, base_png in embeds:
        if any(_rects_heavily_overlap(img_rect, prev) for prev in used):
            continue
        mid = (cap_rect.x0 + cap_rect.x1) / 2
        if not _horiz_ok(cap_rect.x0, cap_rect.x1, img_rect.x0, img_rect.x1, mid):
            # also allow image mid vs caption mid
            imid = (img_rect.x0 + img_rect.x1) / 2
            if not _horiz_ok(img_rect.x0, img_rect.x1, cap_rect.x0, cap_rect.x1, imid):
                continue
        # Caption under image (A)
        if img_rect.y1 <= cap_rect.y0 + 10:
            gap = cap_rect.y0 - img_rect.y1
            if 0 <= gap <= _CAPTION_PAIR_BELOW_PT:
                candidates.append(((0, gap, -img_rect.get_area()), img_rect, base_png, "below"))
        # Caption above image (B)
        if img_rect.y0 >= cap_rect.y1 - 10:
            gap = img_rect.y0 - cap_rect.y1
            if 0 <= gap <= _CAPTION_PAIR_ABOVE_PT:
                candidates.append(((1, gap, -img_rect.get_area()), img_rect, base_png, "above"))
    if not candidates:
        return None
    candidates.sort(key=lambda t: t[0])
    _score, img_rect, base_png, mode = candidates[0]
    return img_rect, base_png, mode


def _orphan_fig_clip(page, cap_rect):
    """design/125 B · 128 — orphan band above caption; x = column width (+bleed)."""
    import fitz

    page_rect = page.rect
    x0, x1 = _column_x_range(page_rect, cap_rect, bleed_frac=0.08)
    y0 = max(page_rect.y0, cap_rect.y0 - _ORPHAN_CLIP_ABOVE_PT)
    y1 = min(page_rect.y1, cap_rect.y1 + 4)
    return fitz.Rect(x0, y0, x1, y1)


def orphan_figure_png_from_caption(page, cap_rect) -> bytes | None:
    """Rasterize vector / missed-body figure band above a caption (design/125 B)."""
    clip = _orphan_fig_clip(page, cap_rect)
    clip |= cap_rect
    return _render_page_clip(page, clip)


def is_caption_only_figure_png(png: bytes) -> bool:
    """True when composite is a thin caption strip (e.g. Azure partial without body)."""
    if len(png) < _MIN_BYTES:
        return False
    from io import BytesIO

    from PIL import Image

    try:
        im = Image.open(BytesIO(png))
        width, height = im.size
    except Exception:  # noqa: BLE001
        return False
    return height <= 400 and width > height * 4


def _column_x_range(page_rect, cap_rect, *, bleed_frac: float = 0.08) -> tuple[float, float]:
    """
    design/128 — map a (possibly narrow) caption to its page column.
    Slight bleed into the other column is intentional (product OK).
    """
    mid = (float(page_rect.x0) + float(page_rect.x1)) / 2.0
    cx = (float(cap_rect.x0) + float(cap_rect.x1)) / 2.0
    bleed = float(page_rect.width) * bleed_frac
    pad = 6.0
    if cx <= mid:
        x0 = float(page_rect.x0) + pad
        x1 = min(float(page_rect.x1) - pad, mid + bleed)
    else:
        x0 = max(float(page_rect.x0) + pad, mid - bleed)
        x1 = float(page_rect.x1) - pad
    # Never thinner than the caption itself.
    x0 = min(x0, float(cap_rect.x0))
    x1 = max(x1, float(cap_rect.x1))
    return x0, x1


def _orphan_table_clip(page, cap_rect):
    """design/128 — clip below table caption using column band (footnotes OK)."""
    import fitz

    page_rect = page.rect
    x0, x1 = _column_x_range(page_rect, cap_rect, bleed_frac=0.10)
    y0 = max(page_rect.y0, float(cap_rect.y0) - 4)
    y1 = min(page_rect.y1, float(cap_rect.y1) + 260)
    return fitz.Rect(x0, y0, x1, y1)


def _extract_embedded_images(
    page, page_index: int, start_i: int
) -> list[tuple[float, float, Figure]]:
    """
    design/125 — caption-first Fig/Scheme extract (+ GA leftover).
    Compound 1a/1b is never split (design/44).
    """
    import fitz

    items: list[tuple[float, float, Figure]] = []
    fig_i = start_i
    embeds = _list_embedded_rects(page)
    used_rects: list[object] = []
    seen_keys: set[str] = set()

    for key, caption, cap_rect in _labeled_caption_hits(
        page, fig_scheme=True, table=False
    ):
        if key in seen_keys:
            continue
        picked = _pick_embed_for_caption(cap_rect, embeds, used_rects)
        if picked is not None:
            img_rect, base_png, mode = picked
            clip = fitz.Rect(img_rect)
            if mode == "below":
                clip |= cap_rect
                clip.y1 = min(page.rect.y1, max(clip.y1, img_rect.y1 + _CAPTION_BELOW_PT))
            else:
                clip |= cap_rect
            rendered = _render_page_clip(page, clip)
            png = rendered if rendered else base_png
            used_rects.append(img_rect)
            sort_y = float(img_rect.y0)
            sort_x = float(img_rect.x0)
        else:
            # B: orphan caption → page clip above caption (vector / missed embed).
            png = orphan_figure_png_from_caption(page, cap_rect)
            if not png:
                continue
            sort_y = float(cap_rect.y0)
            sort_x = float(cap_rect.x0)

        seen_keys.add(key)
        fig_i += 1
        items.append(
            (
                sort_y,
                sort_x,
                Figure(
                    id=f"fig-{fig_i:04d}",
                    image_src=_png_data_url(png),
                    caption=caption,
                    page_index=page_index,
                ),
            )
        )
        if len(items) + start_i >= 200:
            return items

    # Graphical abstract: uncaptioned large early embeds not already used.
    for img_rect, base_png in embeds:
        if any(_rects_heavily_overlap(img_rect, prev) for prev in used_rects):
            continue
        if not _is_graphical_abstract_candidate(page, page_index, img_rect):
            continue
        caption = f"Graphical abstract (p.{page_index + 1})"
        clip = fitz.Rect(img_rect)
        clip.y1 = min(page.rect.y1, img_rect.y1 + _CAPTION_BELOW_PT)
        rendered = _render_page_clip(page, clip)
        png = rendered if rendered else base_png
        used_rects.append(img_rect)
        fig_i += 1
        items.append(
            (
                float(img_rect.y0),
                float(img_rect.x0),
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


def _extract_tables(
    page, page_index: int, start_i: int
) -> list[tuple[float, float, Figure]]:
    """design/125 — Table caption-first; find_tables as attach target."""
    import fitz

    items: list[tuple[float, float, Figure]] = []
    fig_i = start_i
    try:
        finder = page.find_tables()
        tables = list(getattr(finder, "tables", None) or [])
    except Exception:
        tables = []

    table_rects: list[object] = []
    for tab in tables:
        try:
            bbox = fitz.Rect(tab.bbox)
        except Exception:
            continue
        if bbox.width < 40 or bbox.height < 30:
            continue
        table_rects.append(bbox)

    used: list[object] = []
    seen_keys: set[str] = set()

    def _pick_table(cap_rect):
        cands: list[tuple[tuple, object]] = []
        for bbox in table_rects:
            if any(
                (bbox & prev).get_area() > 0.5 * min(bbox.get_area(), prev.get_area())
                for prev in used
            ):
                continue
            mid = (cap_rect.x0 + cap_rect.x1) / 2
            if not _horiz_ok(cap_rect.x0, cap_rect.x1, bbox.x0, bbox.x1, mid):
                continue
            # Caption above table (usual)
            if bbox.y0 >= cap_rect.y1 - 10:
                gap = bbox.y0 - cap_rect.y1
                if 0 <= gap <= _CAPTION_PAIR_ABOVE_PT:
                    cands.append(((0, gap, -bbox.get_area()), bbox))
            # Rare: caption below table
            if bbox.y1 <= cap_rect.y0 + 10:
                gap = cap_rect.y0 - bbox.y1
                if 0 <= gap <= _CAPTION_PAIR_BELOW_PT:
                    cands.append(((1, gap, -bbox.get_area()), bbox))
        if not cands:
            return None
        cands.sort(key=lambda t: t[0])
        return cands[0][1]

    for key, caption, cap_rect in _labeled_caption_hits(
        page, fig_scheme=False, table=True
    ):
        if key in seen_keys:
            continue
        bbox = _pick_table(cap_rect)
        if bbox is not None:
            clip = fitz.Rect(bbox) | cap_rect
            # design/128 — never thinner than the page column band.
            cx0, cx1 = _column_x_range(page.rect, cap_rect, bleed_frac=0.10)
            clip.x0 = min(float(clip.x0), cx0)
            clip.x1 = max(float(clip.x1), cx1)
            used.append(bbox)
            sort_y = float(min(bbox.y0, cap_rect.y0))
            sort_x = float(min(bbox.x0, cap_rect.x0))
        else:
            # Orphan table caption: column-wide clip below caption (design/128).
            clip = _orphan_table_clip(page, cap_rect)
            sort_y = float(cap_rect.y0)
            sort_x = float(cap_rect.x0)

        png = _render_page_clip(page, clip)
        if not png:
            continue
        seen_keys.add(key)
        fig_i += 1
        items.append(
            (
                sort_y,
                sort_x,
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

    # Legacy: tables detected with no caption still get a placeholder (design/02).
    for bbox in table_rects:
        if any(
            (bbox & prev).get_area() > 0.5 * min(bbox.get_area(), prev.get_area())
            for prev in used
        ):
            continue
        caption, cap_rect = _caption_above_table(page, bbox)
        if caption:
            # Already handled by caption-first if punct matched; skip duplicates.
            from sentence_reading.fig_refs import caption_key

            k = caption_key(caption)
            if k and k in seen_keys:
                continue
            if k:
                seen_keys.add(k)
        clip = fitz.Rect(bbox)
        if cap_rect is not None:
            clip |= cap_rect
        else:
            clip.y0 = max(page.rect.y0, clip.y0 - 28)
        png = _render_page_clip(page, clip)
        if not png:
            continue
        used.append(bbox)
        fig_i += 1
        if not caption:
            caption = f"Table (p.{page_index + 1})"
        items.append(
            (
                float(clip.y0),
                float(clip.x0),
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


def _collect_pymupdf_figures(doc) -> list[Figure]:
    """PyMuPDF caption-first extract without cover / validation / id renumber."""
    ordered: list[tuple[tuple, int, float, float, Figure]] = []
    seq = 0

    for page_index, page in enumerate(doc):
        imgs = _extract_embedded_images(page, page_index, seq)
        seq += len(imgs)
        for y0, x0, fig in imgs:
            ordered.append((_caption_sort_key(fig.caption), page_index, y0, x0, fig))

        tables = _extract_tables(page, page_index, seq)
        seq += len(tables)
        for y0, x0, fig in tables:
            ordered.append((_caption_sort_key(fig.caption), page_index, y0, x0, fig))

        if len(ordered) >= 200:
            break

    ordered.sort(key=lambda t: (t[0], t[1], t[2], t[3]))
    from sentence_reading.fig_refs import caption_key

    out: list[Figure] = []
    seen: set[str] = set()
    for _ck, _pi, _y, _x, fig in ordered:
        key = caption_key(fig.caption) or f"raw:{fig.caption[:40]}"
        if key in seen:
            continue
        seen.add(key)
        out.append(fig)
        if len(out) >= 200:
            break
    return out


def _finalize_figure_list(doc, raw: list[Figure]) -> list[Figure]:
    """Sort/dedupe cover prepend, id renumber, caption-lump validation."""
    from sentence_reading.fig_refs import caption_key
    from sentence_reading.pdf.caption_lumps import (
        validate_extracted_figures,
        validate_pages_against_figures,
    )

    slot_backed: list[Figure] = []
    legacy: list[Figure] = []
    for fig in raw or []:
        if (fig.slot_key or "").strip():
            slot_backed.append(fig)
        else:
            legacy.append(fig)

    if slot_backed:
        slot_backed.sort(key=lambda f: _slot_sort_key(f.slot_key))
        to_process = slot_backed
    else:
        legacy.sort(key=lambda f: (_caption_sort_key(f.caption), f.page_index or 0))
        to_process = legacy

    deduped: list[Figure] = []
    seen: set[str] = set()
    for fig in to_process:
        key = (fig.slot_key or "").strip().lower()
        if not key:
            key = caption_key(fig.caption) or f"raw:{fig.caption[:40]}"
        if key in seen:
            continue
        seen.add(key)
        deduped.append(fig)
        if len(deduped) >= 200:
            break
    out = deduped

    cover = _maybe_title_cover_figure(doc)
    if cover is not None:
        cover_key = caption_key(cover.caption) or "title-page"
        if cover_key not in seen:
            out.insert(0, cover)
            if len(out) > 200:
                out = out[:200]

    for i, fig in enumerate(out, start=1):
        ck = caption_key(fig.caption)
        if fig.caption.strip().lower().startswith("title page"):
            prefix = "cov"
        elif fig.id.startswith("tbl-") or (fig.slot_key or "").lower().startswith("table:") or (ck and ck.startswith("table:")):
            prefix = "tbl"
        else:
            prefix = "fig"
        out[i - 1] = Figure(
            id=f"{prefix}-{i:04d}",
            image_src=fig.image_src,
            caption=fig.caption,
            page_index=fig.page_index,
            slot_key=fig.slot_key or "",
            caption_ko=fig.caption_ko,
            caption_ko_stage=fig.caption_ko_stage,
        )

    validate_extracted_figures(out)
    validate_pages_against_figures(doc, out)
    return out


def _extract_figures_pymupdf(pdf_path: Path) -> list[Figure]:
    import fitz

    doc = fitz.open(pdf_path)
    try:
        if doc.is_encrypted:
            raise ValueError("encrypted_pdf")
        return _finalize_figure_list(doc, _collect_pymupdf_figures(doc))
    finally:
        doc.close()


def extract_figures(pdf_path: Path, *, doc_role: str = "main") -> list[Figure]:
    """
    그림(Fig/Scheme) + 표(Table)를 캡션 번호 순으로 합친다 (design/92 · 125).
    design/147 — Azure Layout when configured; PyMuPDF fills missing caption keys.
    design/135 — optional title-page cover prepended as carousel index 0.
    design/152 — supplementary doc_role enables fig:s* slots.
    """
    import fitz
    import logging

    log = logging.getLogger(__name__)

    doc = fitz.open(pdf_path)
    try:
        if doc.is_encrypted:
            raise ValueError("encrypted_pdf")

        merged: list[Figure] = []
        azure_configured = False
        try:
            from sentence_reading.llm.env import azure_document_intelligence_available
            from sentence_reading.pdf.azure_layout import azure_layout_enabled
            from sentence_reading.pdf.extract_figures_v2 import extract_figures_v2

            azure_configured = azure_layout_enabled() and azure_document_intelligence_available()
            if azure_configured:
                merged = extract_figures_v2(pdf_path, doc_role=doc_role)
                if merged:
                    log.info("azure_layout extracted %d figures/tables", len(merged))
                else:
                    log.warning("azure_layout v2 returned 0 slots (no PyMuPDF fallback)")
                return _finalize_figure_list(doc, merged)
        except Exception as exc:
            allow_fb = (os.environ.get("ASR_FIGURE_PYMUPDF_FALLBACK") or "").strip().lower() in (
                "1",
                "true",
                "yes",
                "on",
            )
            if azure_configured and not allow_fb:
                log.error(
                    "azure_layout failed (%s); PyMuPDF fallback disabled (design/154)",
                    exc,
                )
                return _finalize_figure_list(doc, merged)
            if azure_configured and allow_fb:
                log.warning("azure_layout failed (%s); ASR_FIGURE_PYMUPDF_FALLBACK=1", exc)
            else:
                log.warning("azure_layout skipped (%s); using PyMuPDF", exc)

        return _finalize_figure_list(doc, _collect_pymupdf_figures(doc))
    finally:
        doc.close()


def _normalize_page_text(raw: str) -> str:
    raw = re.sub(r"(\w)-\n(\w)", r"\1\2", raw or "")
    raw = re.sub(r"(?<!\n)\n(?!\n)", " ", raw)
    raw = re.sub(r"[ \t]+", " ", raw)
    return raw.strip()


def extract_text_by_page(pdf_path: Path) -> list[str]:
    """
    페이지별 텍스트 (0-based).
    2단이면 블록 좌→우 재정렬 (design/31). 다단 인덱스는 extract_text_by_page_meta.
    """
    pages, _ = extract_text_by_page_meta(pdf_path)
    return pages


def extract_text_by_page_meta(pdf_path: Path) -> tuple[list[str], list[int]]:
    """(pages, multicolumn_page_indices)."""
    from sentence_reading.pdf.reading_order import extract_text_by_page_ordered

    return extract_text_by_page_ordered(pdf_path)


def join_page_texts(pages: list[str]) -> str:
    """페이지 텍스트를 본문 한 덩어리로."""
    return "\n\n".join(p for p in pages if (p or "").strip()).strip()


def extract_text(pdf_path: Path) -> str:
    """페이지 순서 텍스트 (다단 보정 포함)."""
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
