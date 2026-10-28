"""A display equation is kept as a picture of the page (design/481).

Text extraction cannot carry a fraction, a root or a sum: a display equation came out as a
heap of letters and symbols, so `section_flow` drops a box it judges to be display math.
Its page and rectangle were thrown away with it. They are kept here instead, with the
letters of the text just before and just after it, so the equation can be cut from the
PDF and shown under the sentence it follows. Reading aloud, translation and practice see
only the sentence; the picture adds nothing to them.

Placement does not search the paper for a phrase. Equations are placed in reading order,
each looked for after the previous one, by the last letters before it and, failing that,
by the first letters after it.
"""

from __future__ import annotations

import base64
import bisect
import re
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Callable, Iterable, Sequence

# Letters of the neighbouring text kept for placement.
_PROBE = 40
# Two math boxes this close on one page, with no prose between, are one equation.
_JOIN_GAP_PT = 24.0
_PAD_PT = 3.0
# Render scale: 3 × 72 dpi, sharp on a phone at the reader's type size.
ZOOM = 3.0
MAX_EQUATIONS = 150
MAX_PNG_BYTES = 150_000
# All of a paper's equation pictures together, as data URLs. They ride with the
# sentences in every open and every saved copy, so a paper of hundreds stops here.
MAX_PAPER_BYTES = 1_200_000


def _reach(probe: str) -> int:
    """How far past the previous placement a probe this long is trusted."""
    return 30_000 if len(probe) >= 40 else 8_000 if len(probe) >= 24 else 3_000


_EQ_NUMBER = re.compile(r"\(\s*[A-Z]?\d{1,3}[a-z]?\s*\)")
# `2.1.2. Synthesis of Al–Ce–O supports`: its dashes read as math, its number as a heading.
_NUMBERED_HEADING = re.compile(r"^\d+(?:\.\d+)*\.?\s+[A-Z][a-z]")
# Layout roles that are never an equation, whatever their symbols.
_NOT_MATH_ROLES = frozenset(
    {"title", "sectionheading", "pageheader", "pagefooter", "pagenumber", "footnote"}
)


def _role(box) -> str:
    raw = str(getattr(box, "role", "") or "")
    return raw.rsplit(".", 1)[-1].lower().replace("_", "")


def letters(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", re.sub(r"<[^>]+>", "", text or "").lower())


@dataclass(frozen=True)
class EquationBox:
    page: int
    x0: float
    y0: float
    x1: float
    y1: float
    before: str = ""
    after: str = ""
    # Count of prose paragraphs read before it: equations after one paragraph share it.
    para: int = 0


def _near(a, b) -> bool:
    return (
        a.page == b.page
        and b.y0 - a.y1 <= _JOIN_GAP_PT
        and a.y0 - b.y1 <= _JOIN_GAP_PT
    )


def _union(eq: EquationBox, box) -> EquationBox:
    return replace(
        eq,
        x0=min(eq.x0, box.x0),
        y0=min(eq.y0, box.y0),
        x1=max(eq.x1, box.x1),
        y1=max(eq.y1, box.y1),
    )


def collect_equations(
    assigned: Iterable[tuple[str, object]],
    *,
    is_math: Callable[[str], bool],
    keep: Callable[[object], bool],
) -> list[EquationBox]:
    """The display equations among `assigned` (section key, box) in reading order.

    Math boxes next to each other on a page with no prose between are one equation, so
    a column-broken equation and its number `(3)` come out as one picture. A number
    alone, with no equation beside it, is not one.
    """
    out: list[EquationBox] = []
    before = ""
    para = 0
    joinable = False
    lone_number = None
    for key, box in assigned:
        if key == "references":
            before, joinable, lone_number = "", False, None
            continue
        if keep(box) and getattr(box, "kind", "paragraph") == "paragraph":
            text = letters(getattr(box, "text", ""))
            if not text:
                continue
            for i in range(len(out) - 1, -1, -1):
                if out[i].after:
                    break
                out[i] = replace(out[i], after=text[:_PROBE])
            before = text[-_PROBE:]
            para += 1
            joinable, lone_number = False, None
            continue
        raw = " ".join(str(getattr(box, "text", "") or "").split())
        if getattr(box, "kind", "paragraph") != "paragraph" or not raw or not is_math(raw):
            continue
        if _role(box) in _NOT_MATH_ROLES or _NUMBERED_HEADING.match(raw):
            continue
        if box.x1 - box.x0 < 4 or box.y1 - box.y0 < 4:
            continue
        last = out[-1] if out else None
        if joinable and last is not None and _near(last, box):
            out[-1] = _union(last, box)
            continue
        if _EQ_NUMBER.fullmatch(raw):
            lone_number = box
            continue
        eq = EquationBox(box.page, box.x0, box.y0, box.x1, box.y1, before=before, para=para)
        if lone_number is not None and _near(lone_number, box):
            eq = _union(eq, lone_number)
        lone_number = None
        out.append(eq)
        joinable = True
    return out[:MAX_EQUATIONS]


def _probes(text: str, *, tail: bool) -> list[str]:
    out: list[str] = []
    for raw in (text, text.rstrip("0123456789") if tail else text.lstrip("0123456789")):
        for n in (40, 24, 16):
            p = raw[-n:] if tail else raw[:n]
            if len(p) >= 12 and p not in out:
                out.append(p)
    return out


def place_equations(sentence_texts: Sequence[str], boxes: Sequence[EquationBox]) -> list[int]:
    """For each equation, the index of the sentence it follows; -1 when not found."""
    starts: list[int] = []
    owners: list[int] = []
    flat_parts: list[str] = []
    at = 0
    for i, t in enumerate(sentence_texts):
        lt = letters(t)
        if not lt:
            continue
        starts.append(at)
        owners.append(i)
        flat_parts.append(lt)
        at += len(lt)
    flat = "".join(flat_parts)

    def owner(pos: int) -> tuple[int, bool]:
        k = bisect.bisect_right(starts, pos) - 1
        return owners[max(k, 0)], pos == starts[max(k, 0)]

    out: list[int] = []
    cursor = 0
    prev_para, prev_found = -1, -1
    for eq in boxes:
        found = -1
        if eq.before and eq.para == prev_para and prev_found >= 0:
            found = prev_found
        for probe in _probes(eq.before, tail=True) if found < 0 else ():
            p = flat.find(probe, cursor)
            if p >= 0 and p - cursor <= _reach(probe):
                found, _ = owner(p + len(probe) - 1)
                cursor = p + len(probe)
                break
        if found < 0:
            for probe in _probes(eq.after, tail=False):
                p = flat.find(probe, cursor)
                if p >= 0 and p - cursor <= _reach(probe):
                    k, at_start = owner(p)
                    found = owners[max(owners.index(k) - 1, 0)] if at_start else k
                    cursor = p
                    break
        prev_para, prev_found = eq.para, found
        out.append(found if starts else -1)
    return out


def render_equations(
    pdf_path: Path | str,
    boxes: Sequence[EquationBox],
    owners: Sequence[int],
    sentence_ids: Sequence[str],
) -> tuple[dict[str, list[dict]], dict[str, int]]:
    """Equation pictures by sentence id, and a census of what happened to each box."""
    import fitz

    census = {
        "found": len(boxes),
        "placed": 0,
        "unplaced": 0,
        "too_large": 0,
        "bad_box": 0,
        "over_budget": 0,
    }
    spent = 0
    by_sentence: dict[str, list[dict]] = {}
    doc = fitz.open(str(pdf_path))
    try:
        n = 0
        for eq, idx in zip(boxes, owners):
            if not (0 <= idx < len(sentence_ids)):
                census["unplaced"] += 1
                continue
            if not (0 <= eq.page < doc.page_count):
                census["bad_box"] += 1
                continue
            page = doc[eq.page]
            clip = fitz.Rect(
                eq.x0 - _PAD_PT, eq.y0 - _PAD_PT, eq.x1 + _PAD_PT, eq.y1 + _PAD_PT
            ) & page.rect
            if clip.is_empty or clip.width < 6 or clip.height < 4:
                census["bad_box"] += 1
                continue
            pix = page.get_pixmap(
                matrix=fitz.Matrix(ZOOM, ZOOM), clip=clip, colorspace=fitz.csGRAY, alpha=False
            )
            png = pix.tobytes("png")
            if len(png) > MAX_PNG_BYTES:
                census["too_large"] += 1
                continue
            src = "data:image/png;base64," + base64.b64encode(png).decode("ascii")
            if spent + len(src) > MAX_PAPER_BYTES:
                census["over_budget"] += 1
                continue
            spent += len(src)
            n += 1
            census["placed"] += 1
            by_sentence.setdefault(sentence_ids[idx], []).append(
                {
                    "id": f"eq_{n:03d}",
                    "src": src,
                    "w": round(float(clip.width), 1),
                    "h": round(float(clip.height), 1),
                }
            )
    finally:
        doc.close()
    return by_sentence, census


def clean_equations(raw: object) -> tuple[dict, ...]:
    """Stored or received equation rows of one sentence, bounded and shaped."""
    if not isinstance(raw, (list, tuple)):
        return ()
    out: list[dict] = []
    for row in raw[:20]:
        if not isinstance(row, dict):
            continue
        src = str(row.get("src") or "")
        if not src.startswith("data:image/png;base64,") or len(src) > MAX_PNG_BYTES * 2:
            continue
        try:
            w = float(row.get("w") or 0)
            h = float(row.get("h") or 0)
        except (TypeError, ValueError):
            continue
        if w <= 0 or h <= 0:
            continue
        out.append(
            {"id": str(row.get("id") or "")[:16], "src": src, "w": round(w, 1), "h": round(h, 1)}
        )
    return tuple(out)


def attach_equations(pdf_path, sentences, boxes):
    """`sentences` with each placed equation's picture on the sentence it follows."""
    owners = place_equations([getattr(s, "text", "") or "" for s in sentences], boxes)
    ids = [str(getattr(s, "id", "") or "") for s in sentences]
    by_sentence, census = render_equations(pdf_path, boxes, owners, ids)
    out = [
        replace(s, equations=tuple(by_sentence[s.id])) if s.id in by_sentence else s
        for s in sentences
    ]
    return out, census
