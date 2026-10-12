"""design/398 — does the paper print any body heading at all?

An Adv Mater Communication prints only `Supporting Information` and
`Acknowledgements`, so every sentence lands in one Body section. That is the paper's
shape, and the `high_body_ratio` warning should not call it a failed split. The
answer comes from the layout service's own `sectionHeading` tags, measured on three
papers: 0 body headings on the Communication, 14 on an Elsevier article, 3 on an
ACS one.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable

from sentence_reading.pdf.section_flow import (
    FlowBox,
    OrderedPaper,
    boxes_from_azure_result,
    header_key,
    norm_role,
    order_boxes,
)

_NOT_BODY = frozenset(
    {"title", "abstract", "references", "acknowledgement", "appendix", "declaration", "credit"}
)
_BODY = frozenset(
    {"introduction", "experimental", "methods", "results", "discussion", "conclusion", "body"}
)
_APPARATUS = re.compile(
    r"^\s*(?:supporting information|supplementary (?:information|materials?|data)"
    r"|key\s?words?|conflicts? of interest|competing (?:financial )?interests?"
    r"|author contributions?|author information|data availability|funding|notes"
    r"|abbreviations|associated content)\b",
    re.IGNORECASE,
)


def body_heading_n(boxes: Iterable[FlowBox]) -> int:
    n = 0
    for box in boxes:
        text = " ".join((box.text or "").split())
        if not text or _APPARATUS.match(text):
            continue
        key = header_key(text)
        if norm_role(box.role) == "sectionheading":
            if key not in _NOT_BODY:
                n += 1
        elif key in _BODY and len(text) < 80:
            n += 1
    return n


def ordered_with_body_headings(pdf_path: Path) -> tuple[OrderedPaper | None, int | None]:
    """`azure_ordered_pages`, plus the body heading count from the same analyze call."""
    from sentence_reading.llm.env import azure_document_intelligence_available
    from sentence_reading.pdf.azure_layout import azure_layout_enabled

    if not azure_layout_enabled() or not azure_document_intelligence_available():
        return None, None

    import fitz

    from sentence_reading.pdf.layout_map import analyze_layout_map

    doc = fitz.open(pdf_path)
    text_census: dict[str, int] = {}
    try:
        _layout, _client, result = analyze_layout_map(pdf_path)
        boxes, pages = boxes_from_azure_result(result, doc, text_census=text_census)
    finally:
        doc.close()
    heads = body_heading_n(boxes)
    ordered = order_boxes(boxes, pages)
    ordered.text_census = text_census
    return ordered, heads
