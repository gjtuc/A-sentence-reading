"""
design/137 — split multiple Fig/Table/Scheme captions on one line into separate slots.

WHY: one lump → wrong carousel index / missing Fig jump targets.
Fail-closed: label signals without a clean split → refuse ingest (no silent lump success).
"""

from __future__ import annotations

import os
import re

from sentence_reading.fig_refs import caption_key

# Label token start (no end-of-line anchor — findall for multi-caption lines).
_CAPTION_LABEL_POS = re.compile(
    r"(?i)(?:^|(?<![A-Za-z])\s+)((?:Fig(?:ure)?|Scheme|Table)\.?\s*S?\d+[a-z]?\b)"
)
# Single-caption suffix from first label (design/127 compat).
_CAPTION_INLINE_TAIL = re.compile(
    r"(?i)(?:^|(?<![A-Za-z])\s+)((?:Fig(?:ure)?|Scheme|Table)\.?\s*S?\d+[a-z]?\b.*)$"
)


class CaptionLumpError(ValueError):
    """User-facing ingest refusal when caption lumps cannot be split safely."""


def split_caption_lumps_enabled() -> bool:
    """Kill switch: ASR_SPLIT_CAPTION_LUMPS=0 restores pre-137 lump behavior."""
    v = (os.environ.get("ASR_SPLIT_CAPTION_LUMPS") or "1").strip().lower()
    return v not in ("0", "false", "off", "no")


def count_inline_labels(text: str) -> int:
    """How many caption labels appear on this line (not body refs like ``in Fig. 3``)."""
    return len(list(_CAPTION_LABEL_POS.finditer((text or "").replace("\x00", ""))))


def split_line_caption_segments(text: str) -> list[str]:
    """Split one rebuilt line into per-label caption segments (design/137).

    WHY: ``_CAPTION_INLINE_START.search`` only kept the first label on a line.
    """
    raw = (text or "").replace("\x00", "").strip()
    if not raw:
        return []
    matches = list(_CAPTION_LABEL_POS.finditer(raw))
    if not matches:
        return [raw]
    if len(matches) == 1:
        m = _CAPTION_INLINE_TAIL.search(raw)
        return [m.group(1).strip()] if m else [raw]
    out: list[str] = []
    for i, m in enumerate(matches):
        start = m.start(1)
        end = matches[i + 1].start(1) if i + 1 < len(matches) else len(raw)
        seg = raw[start:end].strip()
        if seg:
            out.append(seg)
    return out


def distinct_caption_keys_in_text(text: str) -> list[str]:
    """Distinct fig/table/scheme keys from inline segments (ordered)."""
    seen: set[str] = set()
    out: list[str] = []
    for seg in split_line_caption_segments(text):
        k = caption_key(seg)
        if k and k not in seen:
            seen.add(k)
            out.append(k)
    return out


def _segment_has_caption_body(seg: str, *, min_letters: int = 3) -> bool:
    """True when text after the label looks like a real caption title (not bare ``Fig. 2``)."""
    from sentence_reading.pdf.extract import _CAPTION_LABEL

    raw = (seg or "").strip()
    m = _CAPTION_LABEL.match(raw)
    if not m:
        return False
    rest = raw[m.end() :].lstrip(" \t.:;·\u2013\u2014-")
    letters = sum(1 for c in rest if c.isalpha())
    return letters >= min_letters


def maybe_fail_ambiguous_line(
    line_text: str,
    valid_heads: list[tuple[int, str]],
    *,
    is_caption_line,
) -> None:
    """Fail-closed when label count ≥2 but not every label became a valid caption."""
    if not split_caption_lumps_enabled():
        return
    n_labels = count_inline_labels(line_text)
    if n_labels < 2:
        return
    # Every label position must map to a validated caption head.
    if len(valid_heads) < n_labels:
        raise CaptionLumpError(
            "한 줄에 여러 그림·표 캡션이 있는데 구분하지 못했습니다. "
            "PDF를 확인하거나 다른 파일로 올려 주세요."
        )
    # WHY: bare ``Fig. 2`` passes soft-caption heuristics but is not a splittable lump.
    for _idx, head in valid_heads:
        if not _segment_has_caption_body(head):
            raise CaptionLumpError(
                "한 줄에 여러 그림·표 캡션이 있는데 구분하지 못했습니다. "
                "PDF를 확인하거나 다른 파일로 올려 주세요."
            )
    # Double-check each segment that looked like a label.
    for seg in split_line_caption_segments(line_text):
        if count_inline_labels(seg) >= 1 and not is_caption_line(seg):
            raise CaptionLumpError(
                "한 줄에 여러 그림·표 캡션이 있는데 구분하지 못했습니다. "
                "PDF를 확인하거나 다른 파일로 올려 주세요."
            )


def validate_extracted_figures(figures) -> None:
    """Post-extract guard: no figure caption may still contain multiple keys."""
    if not split_caption_lumps_enabled():
        return
    for fig in figures or []:
        cap = getattr(fig, "caption", None) or ""
        keys = distinct_caption_keys_in_text(str(cap))
        if len(keys) >= 2:
            raise CaptionLumpError(
                "그림·표 캡션이 한 덩어리로 남아 처리할 수 없습니다. "
                "PDF 레이아웃을 확인하거나 다른 파일로 올려 주세요."
            )


def validate_pages_against_figures(doc, figures) -> None:
    """Fail when a page line shows ≥2 caption labels but extract missed a key."""
    if not split_caption_lumps_enabled():
        return
    from sentence_reading.pdf.extract import _is_caption_line, _page_caption_lines

    def _any_cap(s: str) -> bool:
        return _is_caption_line(s, fig_scheme=True, table=False) or _is_caption_line(
            s, fig_scheme=False, table=True
        )

    extracted: set[str] = set()
    for fig in figures or []:
        k = caption_key(getattr(fig, "caption", None) or "")
        if k:
            extracted.add(k)

    for page in doc:
        for text, _rect in _page_caption_lines(page):
            if count_inline_labels(text) < 2:
                continue
            want: list[str] = []
            for seg in split_line_caption_segments(text):
                if _any_cap(seg):
                    k = caption_key(seg)
                    if k:
                        want.append(k)
            if len(want) < 2:
                maybe_fail_ambiguous_line(
                    text,
                    [(i, seg) for i, seg in enumerate(split_line_caption_segments(text)) if _any_cap(seg)],
                    is_caption_line=_any_cap,
                )
                continue
            missing = [k for k in want if k not in extracted]
            if missing:
                raise CaptionLumpError(
                    "한 줄에 여러 그림·표 캡션이 있는데 모두 추출하지 못했습니다. "
                    "PDF를 확인하거나 다른 파일로 올려 주세요."
                )
