"""
Azure layout boxes → section reading order.

Page center, not the median of box centers, decides a band versus a column.
A right-side header with no left body neighbor (ABSTRACT) is read before the
next left header. A left numbered header keeps left text above it in the
previous section, then reads that column down and the right column from the
top. Subheads (2.1) are cards, not new sections. References are not practice
text. Missing Azure is not replaced here.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

SECTION_MARK = "<<<ASR_SECTION {key}>>>"
_MARK_RE = re.compile(r"<<<ASR_SECTION ([a-z][a-z0-9_]*)>>>")

_SUBHEAD = re.compile(r"^\d+\.\d+\b")
# design/325 — `Abstract` then a separator then the abstract text itself.
# A bare `Abstract` heading is handled by the exact match below; this pattern
# needs the separator so a body sentence opening with the word cannot match.
_ABSTRACT_RUN_IN = re.compile(
    r"^abstract\s*[-\u2010-\u2015\u2212:\u00b7\u2013\u2014]\s*\S"
)
_CHROME = re.compile(
    r"(article\s+info|a r t i c l e\s+i n f o|keywords?\b|graphical\s+abstract|"
    r"copyright|all rights reserved|©|\(c\)\s*\d{4}|corresponding author|"
    r"e-mail:|email:)",
    re.IGNORECASE,
)
def norm_role(role: str) -> str:
    raw = str(role or "")
    if "." in raw:
        raw = raw.rsplit(".", 1)[-1]
    return raw.lower().replace("_", "")


@dataclass
class FlowBox:
    page: int
    x0: float
    y0: float
    x1: float
    y1: float
    text: str
    role: str = ""
    kind: str = "paragraph"


@dataclass
class OrderedPaper:
    pages: list[str]
    marked_text: str
    sections: list[tuple[str, str]] = field(default_factory=list)
    references_text: str = ""


def section_mark(key: str) -> str:
    return SECTION_MARK.format(key=key)


def pinned_section(chunk: str) -> str | None:
    m = _MARK_RE.search(chunk or "")
    return m.group(1) if m else None


def strip_section_mark(chunk: str) -> str:
    return _MARK_RE.sub("", chunk or "").strip()


def header_key(text: str) -> str | None:
    line = re.sub(r"\s+", " ", ((text or "").strip().splitlines() or [""])[0]).strip()
    if not line:
        return None
    # design/325 — journals run the abstract straight into its own heading:
    # `Abstract−In order to...` (Springer) and `ABSTRACT: A series of...` (ACS).
    # Azure hands the abstract back as one long paragraph, so this has to be
    # decided before the standalone-heading length guard, or the abstract never
    # opens a section and inherits whichever one is already open.
    if _ABSTRACT_RUN_IN.match(line.lower()):
        return "abstract"
    if len(line) > 120 or _SUBHEAD.match(line):
        return None
    bare = re.sub(r"^\d+\.\s*", "", line).strip()
    low = bare.lower()
    # `A B S T R A C T` — Elsevier letter-spaces the heading, like `a r t i c l e`.
    if low == "abstract" or re.sub(r"\s+", "", low) == "abstract":
        return "abstract"
    if low.startswith("introduction"):
        return "introduction"
    if low.startswith("experimental") or low.startswith("materials and methods"):
        return "experimental"
    if low == "methods" or low.startswith("methods "):
        return "methods"
    if low.startswith("results"):
        return "results"
    # "4. Further analysis and discussion" is discussion; "results and
    # discussions" already returned above.
    if "discussion" in low and "results" not in low:
        return "discussion"
    if low.startswith("conclusion"):
        return "conclusion"
    if low.startswith("reference") or low.startswith("bibliography"):
        return "references"
    if low.startswith("acknowledg"):
        return "acknowledgement"
    if low.startswith("appendix"):
        return "appendix"
    if low.startswith("declaration"):
        return "declaration"
    if low.startswith("credit") or "authorship contribution" in low:
        return "credit"
    if re.match(r"^\d+\.\s+\S", line) and len(line) < 80 and _looks_like_heading(line):
        return "body"
    return None


def _looks_like_heading(line: str) -> bool:
    """A numbered section title, not a bibliography entry '1. Smith, 2020.'."""
    if re.search(r"\[|doi|https?://|www\.", line, re.IGNORECASE):
        return False
    if line.count(",") >= 2 or re.search(r"\b(?:19|20)\d{2}\b", line):
        return False
    words = re.findall(r"[A-Za-z]{2,}", line)
    return 1 <= len(words) <= 12


def _is_bibliography_line(text: str) -> bool:
    line = re.sub(r"\s+", " ", text or "").strip()
    if re.match(r"^\[\d+\]\s+\S", line):
        return True
    return bool(
        re.match(r"^\d+\.\s+[A-Z]", line) and re.search(r"\b(?:19|20)\d{2}\b", line)
    )


def _retag_bibliography_runs(
    assigned: list[tuple[str, FlowBox]],
) -> list[tuple[str, FlowBox]]:
    """design/332 — a reference list with no heading is still a reference list.

    Wiley prints the numbered list straight after `Acknowledgements` with no
    `References` line, so `header_key` never opens a references section and the
    entries became practice sentences: 106 of 496 on one Adv Mater review, more
    than one sentence in five asking the reader to say
    `A. Author, B. Author, Adv. Mater. 2019, 31, 1234` aloud.

    Two consecutive bibliography lines switch the section. An explicit heading
    always wins, so a journal that prints Methods after References recovers.
    """
    out: list[tuple[str, FlowBox]] = []
    run = 0
    in_refs = False
    for key, box in assigned:
        hk = header_key(box.text)
        if hk:
            # A real heading decides, in both directions.
            in_refs = hk == "references"
            run = 0
            out.append((key, box))
            continue
        if _is_bibliography_line(box.text):
            run += 1
            if run >= 2:
                in_refs = True
        else:
            run = 0
        out.append(("references" if in_refs else key, box))

    if not any(k == "references" for k, _ in out):
        return assigned
    # Retag the first line of a run that only tipped over on the second.
    for i in range(1, len(out)):
        if out[i][0] == "references" and out[i - 1][0] != "references":
            if _is_bibliography_line(out[i - 1][1].text):
                out[i - 1] = ("references", out[i - 1][1])
    return out


def crosses_center(box: FlowBox, width: float, margin: float = 12.0) -> bool:
    center = width / 2.0
    return box.x0 < center - margin and box.x1 > center + margin


def _drop_chrome(box: FlowBox, *, page_height: float) -> bool:
    kind = (box.kind or "").lower()
    if kind.startswith("figure") or kind.startswith("table"):
        return True
    role = norm_role(box.role)
    if role in ("pageheader", "pagefooter", "pagenumber"):
        return True
    text = re.sub(r"\s+", " ", box.text or "").strip()
    if not text:
        return True
    # Azure tags the bottom of a references column as a footnote. Keep
    # bibliography lines; drop real notes (corresponding author, etc.).
    if role == "footnote" and not _is_bibliography_line(text):
        return True
    if _CHROME.search(text):
        return True
    if header_key(text):
        return False
    if box.y0 < 140 and "elsevier" in text.lower():
        return True
    return False


def _drop_inside_figures(boxes: list[FlowBox]) -> list[FlowBox]:
    figs = [b for b in boxes if (b.kind or "").startswith("figure")]
    out: list[FlowBox] = []
    for box in boxes:
        if (box.kind or "").startswith(("figure", "table")):
            continue
        area = max(0.0, box.x1 - box.x0) * max(0.0, box.y1 - box.y0)
        if area <= 0:
            continue
        buried = False
        for fig in figs:
            if fig.page != box.page:
                continue
            ix0 = max(box.x0, fig.x0)
            iy0 = max(box.y0, fig.y0)
            ix1 = min(box.x1, fig.x1)
            iy1 = min(box.y1, fig.y1)
            inter = max(0.0, ix1 - ix0) * max(0.0, iy1 - iy0)
            if inter / area >= 0.6:
                buried = True
                break
        if not buried:
            out.append(box)
    return out


def _is_sidebar(header: FlowBox, page_boxes: list[FlowBox], width: float) -> bool:
    # ABSTRACT is a parallel column even when Azure's polygon runs wide.
    if header_key(header.text) != "abstract":
        return False
    if header.x0 < width * 0.2:
        return False
    for other in page_boxes:
        if other is header:
            continue
        if other.y1 < header.y0 - 4 or other.y0 > header.y1 + 8:
            continue
        if other.x1 < header.x0 - 6 and header_key(other.text) is None and norm_role(other.role) != "title":
            return False
    return True


def _front_matter(boxes: list[FlowBox]) -> list[FlowBox]:
    """Drop authors and article-info sitting above ABSTRACT on page 0."""
    abstract = next(
        (b for b in boxes if b.page == 0 and header_key(b.text) == "abstract"),
        None,
    )
    if abstract is None:
        return boxes
    title = next((b for b in boxes if b.page == 0 and norm_role(b.role) == "title"), None)
    if title is None:
        cands = [
            b
            for b in boxes
            if b.page == 0 and b.y1 <= abstract.y0 + 4 and len(b.text) > 40
        ]
        if cands:
            title = max(cands, key=lambda b: (b.x1 - b.x0) * len(b.text))
            title.role = "title"
    out: list[FlowBox] = []
    for box in boxes:
        if (
            box.page == 0
            and box.y0 < abstract.y0 - 2
            and box is not title
            and norm_role(box.role) != "title"
            and header_key(box.text) is None
        ):
            continue
        out.append(box)
    return out


def _take(out: list[tuple[str, FlowBox]], seen: set[int], box: FlowBox, key: str) -> None:
    if id(box) in seen:
        return
    seen.add(id(box))
    out.append((key, box))


def join_section_text(parts: list[str]) -> str:
    """Glue a column break that split one sentence. Drop display math."""
    cards: list[str] = []
    buf = ""

    def flush() -> None:
        nonlocal buf
        piece = buf.strip()
        if piece:
            cards.append(piece)
        buf = ""

    i = 0
    cleaned = [re.sub(r"\s+", " ", p).strip() for p in parts if (p or "").strip()]
    while i < len(cleaned):
        raw = cleaned[i]
        i += 1
        if _is_display_math(raw):
            continue
        if _SUBNUM.match(raw) and i < len(cleaned):
            nxt = cleaned[i]
            if nxt and not _is_display_math(nxt) and _prose_words(nxt) <= 8 and len(nxt) < 80:
                raw = f"{raw.rstrip('.')} {nxt}"
                i += 1
        if not buf:
            buf = raw
            continue
        if _SENT_END.search(buf):
            flush()
            buf = raw
        else:
            buf = f"{buf} {raw}"
    flush()
    return "\n\n".join(cards)


def _keep_as_sentence(box: FlowBox) -> bool:
    text = re.sub(r"\s+", " ", box.text or "").strip()
    if not text or re.fullmatch(r"\d+\.?", text):
        return False
    if header_key(text) and len(text) < 80:
        return False
    if _is_display_math(text):
        return False
    return True


_SUBNUM = re.compile(r"^\d+\.\d+\.?$")
_EQ_END = re.compile(r"\(\d+\)\s*$")
_SENT_END = re.compile(r"[.!?]\s*$")


def _prose_words(text: str) -> int:
    return len(re.findall(r"[A-Za-z]{3,}", text or ""))


def _is_display_math(text: str) -> bool:
    raw = re.sub(r"\s+", " ", text or "").strip()
    if not raw or header_key(raw) or _SUBNUM.match(raw):
        return False
    if re.match(r"^\[\d+\]", raw):
        return False
    words = _prose_words(raw)
    symbols = sum(1 for c in raw if c in "=+-*/<>()[]{}^_")
    if _EQ_END.search(raw) and words < 6:
        return True
    if words < 3 and symbols >= 2:
        return True
    # Column-broken equation: "tion =" or "O 2 = exp AH ...", not prose.
    if "=" in raw and words <= 6 and len(raw) < 180:
        if not re.search(
            r"\b(the|and|with|that|this|were|was|are|from|for|which|where)\b",
            raw,
            re.IGNORECASE,
        ):
            return True
    return False


def _read_page(
    page_boxes: list[FlowBox],
    *,
    width: float,
    height: float,
    previous: str | None,
) -> list[tuple[str, FlowBox]]:
    headers = [b for b in page_boxes if header_key(b.text)]
    headers.sort(key=lambda b: (b.y0, b.x0))
    sidebars = [h for h in headers if _is_sidebar(h, page_boxes, width)]
    left_headers = [
        h
        for h in headers
        if h not in sidebars and (h.x0 + h.x1) / 2.0 < width / 2.0
    ]
    seen: set[int] = set()
    out: list[tuple[str, FlowBox]] = []

    for box in sorted(page_boxes, key=lambda b: (b.y0, b.x0)):
        if norm_role(box.role) == "title":
            _take(out, seen, box, "title")

    next_left_y = min((h.y0 for h in left_headers), default=height + 1)
    for header in sidebars:
        key = header_key(header.text) or "body"
        _take(out, seen, header, key)
        for box in sorted(page_boxes, key=lambda b: (b.y0, b.x0)):
            if id(box) in seen or box.y0 >= next_left_y - 2 or box.y1 < header.y0 - 2:
                continue
            if box.x0 >= header.x0 - 24 or crosses_center(box, width):
                _take(out, seen, box, key)

    if left_headers and previous:
        first_y = left_headers[0].y0
        for box in sorted(page_boxes, key=lambda b: (b.y0, b.x0)):
            if id(box) in seen or box.y0 >= first_y - 2:
                continue
            if box.x1 <= width / 2.0 + 8:
                _take(out, seen, box, previous)

    current = previous or "body"
    for i, header in enumerate(left_headers):
        key = header_key(header.text) or current
        y_end = left_headers[i + 1].y0 if i + 1 < len(left_headers) else height + 1
        _take(out, seen, header, key)
        left_col = [
            b
            for b in page_boxes
            if id(b) not in seen
            and header.y0 - 2 <= b.y0 < y_end - 2
            and not crosses_center(b, width)
            and (b.x0 + b.x1) / 2.0 < width / 2.0
        ]
        for box in sorted(left_col, key=lambda b: (b.y0, b.x0)):
            hk = header_key(box.text)
            if hk:
                key = hk
            _take(out, seen, box, key)
        # The last left header on the page owns the right column from the top.
        # An earlier header only owns its left slice; the later header's
        # right-column continuation sits above that later header.
        if i == len(left_headers) - 1:
            right_col = [
                b
                for b in page_boxes
                if id(b) not in seen
                and not crosses_center(b, width)
                and (b.x0 + b.x1) / 2.0 >= width / 2.0
            ]
            for box in sorted(right_col, key=lambda b: (b.y0, b.x0)):
                hk = header_key(box.text)
                if hk:
                    key = hk
                _take(out, seen, box, key)
            current = key

    rest = [b for b in page_boxes if id(b) not in seen]
    if rest:
        key = out[-1][0] if out else (previous or "body")
        left = [
            b
            for b in rest
            if not crosses_center(b, width) and (b.x0 + b.x1) / 2.0 < width / 2.0
        ]
        bands = [b for b in rest if crosses_center(b, width)]
        right = [b for b in rest if b not in left and b not in bands]
        stream = sorted(left + bands, key=lambda b: (b.y0, b.x0)) + sorted(
            right, key=lambda b: (b.y0, b.x0)
        )
        for box in stream:
            hk = header_key(box.text)
            if hk:
                key = hk
            _take(out, seen, box, key)
            current = key
    return out


def order_boxes(boxes: list[FlowBox], pages: list[dict]) -> OrderedPaper:
    by_page: dict[int, list[FlowBox]] = {}
    figs = [b for b in boxes if (b.kind or "").startswith("figure")]
    tables = [b for b in boxes if (b.kind or "").startswith("table")]
    cleaned: list[FlowBox] = []
    for box in boxes:
        height = float((pages[box.page] if box.page < len(pages) else {}).get("height") or 800)
        if _drop_chrome(box, page_height=height):
            continue
        cleaned.append(box)
    cleaned = _drop_inside_figures(figs + cleaned)
    kept: list[FlowBox] = []
    for box in cleaned:
        cx = (box.x0 + box.x1) / 2.0
        cy = (box.y0 + box.y1) / 2.0
        buried = False
        for table in tables:
            if table.page != box.page:
                continue
            if not (table.x0 <= cx <= table.x1 and table.y0 <= cy <= table.y1):
                continue
            if header_key(box.text):
                continue
            wide = (table.x1 - table.x0) > 400
            if wide and len(box.text or "") > 200:
                continue
            buried = True
            break
        if not buried:
            kept.append(box)
    cleaned = _front_matter(kept)
    for box in cleaned:
        by_page.setdefault(box.page, []).append(box)

    previous: str | None = None
    assigned: list[tuple[str, FlowBox]] = []
    n_pages = max(len(pages), max((b.page for b in boxes), default=-1) + 1)
    for i in range(n_pages):
        width = float((pages[i] if i < len(pages) else {}).get("width") or 595)
        height = float((pages[i] if i < len(pages) else {}).get("height") or 842)
        page_assigned = _read_page(
            by_page.get(i, []),
            width=width,
            height=height,
            previous=previous,
        )
        assigned.extend(page_assigned)
        if page_assigned:
            previous = page_assigned[-1][0]

    assigned = _retag_bibliography_runs(assigned)

    sections: list[tuple[str, list[str]]] = []
    page_parts: list[list[str]] = [[] for _ in range(n_pages)]
    open_key = ""
    for key, box in assigned:
        if key != open_key:
            sections.append((key, []))
            open_key = key
            if box.page < len(page_parts):
                page_parts[box.page].append(section_mark(key))
        sections[-1][1].append(box.text.strip()) if _keep_as_sentence(box) else None
        if box.page < len(page_parts) and _keep_as_sentence(box):
            page_parts[box.page].append(box.text.strip())

    body: list[tuple[str, str]] = []
    refs: list[str] = []
    for key, parts in sections:
        text = join_section_text(parts)
        if not text:
            continue
        if key == "references":
            refs.append(text)
        else:
            body.append((key, text))

    marked_parts = [f"{section_mark(key)}\n{text}" for key, text in body]
    references_text = "\n\n".join(refs).strip()
    if references_text:
        if not re.match(r"(?i)references\b", references_text):
            references_text = "References\n" + references_text
        marked_parts.append(f"{section_mark('references')}\n{references_text}")
    return OrderedPaper(
        pages=["\n\n".join(p for p in parts if p).strip() for p in page_parts],
        marked_text="\n\n".join(marked_parts).strip(),
        sections=body,
        references_text=references_text,
    )


def boxes_from_azure_result(result, doc) -> tuple[list[FlowBox], list[dict]]:
    from sentence_reading.pdf.layout_map import (
        _classify_paragraph_caption,
        _figure_caption_text,
        _region_page_and_rect,
        build_layout_map_from_result,
    )

    layout = build_layout_map_from_result(result, doc)
    pages = [
        {"width": float(p.get("width_pt") or 595), "height": float(p.get("height_pt") or 842)}
        for p in layout.pages
    ]
    boxes: list[FlowBox] = []
    for para in result.paragraphs or []:
        page_index, rect = _region_page_and_rect(getattr(para, "bounding_regions", None) or [])
        if page_index is None or rect is None:
            continue
        text = (getattr(para, "content", None) or "").strip()
        kind = _classify_paragraph_caption(text) or "paragraph"
        boxes.append(
            FlowBox(
                page=page_index,
                x0=rect["x0"],
                y0=rect["y0"],
                x1=rect["x1"],
                y1=rect["y1"],
                text=text,
                role=str(getattr(para, "role", None) or ""),
                kind=kind,
            )
        )
    for figure in result.figures or []:
        page_index, rect = _region_page_and_rect(getattr(figure, "bounding_regions", None) or [])
        if page_index is None or rect is None:
            continue
        boxes.append(
            FlowBox(
                page=page_index,
                x0=rect["x0"],
                y0=rect["y0"],
                x1=rect["x1"],
                y1=rect["y1"],
                text=_figure_caption_text(figure),
                kind="figure_body",
            )
        )
    for table in result.tables or []:
        page_index, rect = _region_page_and_rect(getattr(table, "bounding_regions", None) or [])
        if page_index is None or rect is None:
            continue
        boxes.append(
            FlowBox(
                page=page_index,
                x0=rect["x0"],
                y0=rect["y0"],
                x1=rect["x1"],
                y1=rect["y1"],
                text="",
                kind="table_body",
            )
        )
    return boxes, pages


def azure_ordered_pages(pdf_path: Path) -> OrderedPaper | None:
    """None when Azure is off or unconfigured. Does not fall back to PyMuPDF."""
    from sentence_reading.llm.env import azure_document_intelligence_available
    from sentence_reading.pdf.azure_layout import azure_layout_enabled

    if not azure_layout_enabled() or not azure_document_intelligence_available():
        return None

    from sentence_reading.pdf.layout_map import analyze_layout_map

    import fitz

    doc = fitz.open(pdf_path)
    try:
        _layout, _client, result = analyze_layout_map(pdf_path)
        boxes, pages = boxes_from_azure_result(result, doc)
    finally:
        doc.close()
    return order_boxes(boxes, pages)
