"""
design/302 — lock Azure boxes before editing reading order.

Prints booleans and counts only. Paper text stays off the console.
"""

from __future__ import annotations

import re
from typing import Any

from sentence_reading.pdf.section_flow import (
    FlowBox,
    OrderedPaper,
    header_key,
    norm_role,
    order_boxes,
)

_KNOWN_ROLES = {
    "",
    "pageheader",
    "pagefooter",
    "pagenumber",
    "footnote",
    "title",
    "sectionheading",
}


def role_parse_ok(raw_roles: list[str]) -> bool:
    """True only after enum names like ParagraphRole.PAGE_HEADER are stripped."""
    if not raw_roles:
        return False
    saw = False
    for raw in raw_roles:
        text = str(raw or "")
        if not text:
            continue
        saw = True
        if "_" in text and "." not in text:
            return False
        norm = norm_role(text)
        if "paragraphrole" in norm or "_" in norm:
            return False
        if norm not in _KNOWN_ROLES:
            return False
    return saw


def inventory_row(box: FlowBox) -> dict[str, Any]:
    """Coordinates and flags. No paper text."""
    text = box.text or ""
    low = text.lower()
    return {
        "page": box.page,
        "x0": round(box.x0, 1),
        "y0": round(box.y0, 1),
        "x1": round(box.x1, 1),
        "y1": round(box.y1, 1),
        "role": norm_role(box.role),
        "kind": box.kind,
        "n": len(text),
        "header": header_key(text),
        "elsevier": "elsevier" in low or "©" in text,
    }


def elsevier_front_boxes() -> tuple[list[FlowBox], list[dict]]:
    """Azure geometry, not the visual guess. ABSTRACT polygon crosses page center."""
    boxes = [
        FlowBox(0, 234, 35, 359, 55, "journal", role="ParagraphRole.PAGE_HEADER"),
        FlowBox(0, 36, 165, 479, 200, "title prose", role="ParagraphRole.TITLE"),
        FlowBox(0, 36, 209, 349, 230, "A. Author"),
        FlowBox(0, 32, 254, 158, 280, "ARTICLE INFO"),
        FlowBox(0, 158, 255, 561, 286, "ABSTRACT", role="ParagraphRole.SECTION_HEADING"),
        FlowBox(0, 158, 287, 561, 372, "High-performance cathode body starts here."),
        FlowBox(0, 32, 287, 158, 340, "Keywords: foo"),
        FlowBox(0, 37, 396, 98, 412, "1. Introduction", role="ParagraphRole.SECTION_HEADING"),
        FlowBox(0, 36, 416, 290, 500, "Left introduction prose."),
        FlowBox(0, 305, 395, 558, 500, "Right introduction prose."),
        FlowBox(0, 37, 725, 469, 760, "Copyright line Elsevier", role="ParagraphRole.PAGE_FOOTER"),
    ]
    pages = [{"width": 595.0, "height": 792.0}]
    return boxes, pages


def experimental_boxes() -> tuple[list[FlowBox], list[dict]]:
    boxes = [
        FlowBox(0, 38, 100, 220, 120, "1. Introduction"),
        FlowBox(0, 38, 130, 250, 180, "Intro body."),
        FlowBox(1, 38, 80, 250, 120, "End of introduction."),
        FlowBox(1, 38, 261, 220, 280, "2. Experimental"),
        FlowBox(1, 38, 429, 250, 500, "2.2 Synthesis text"),
        FlowBox(1, 307, 50, 560, 110, "followed by co-sintering"),
        FlowBox(1, 307, 129, 560, 200, "2.3 later step"),
    ]
    pages = [{"width": 595.0, "height": 792.0}, {"width": 595.0, "height": 792.0}]
    return boxes, pages


def references_boxes() -> tuple[list[FlowBox], list[dict]]:
    """Right-column entry sits above the left References header."""
    boxes = [
        FlowBox(0, 38, 80, 250, 100, "Declaration"),
        FlowBox(0, 38, 110, 250, 160, "No competing interests."),
        FlowBox(0, 36, 269, 120, 290, "References", role="ParagraphRole.SECTION_HEADING"),
        FlowBox(0, 306, 53, 556, 120, "[20] A. Cite."),
        FlowBox(0, 36, 300, 250, 360, "[1] B. Cite."),
    ]
    pages = [{"width": 595.0, "height": 792.0}]
    return boxes, pages


def checklist(ordered: OrderedPaper) -> dict[str, Any]:
    from sentence_reading.pdf.sentences import split_into_sentences

    practice: list[tuple[str, str]] = []
    for key, text in ordered.sections:
        for sent in split_into_sentences(text):
            piece = (sent.text or "").strip()
            if piece:
                practice.append((key, piece))
    blob = "\n".join(text for _k, text in practice)
    abs_rows = [text for key, text in practice if key == "abstract"]
    intro = [text for key, text in practice if key == "introduction"]
    exp = "\n".join(text for key, text in practice if key == "experimental")
    results = [text for key, text in practice if key == "results"]
    nums = {int(m) for m in re.findall(r"\[(\d+)\]", ordered.references_text or "")}
    missing = [n for n in range(1, (max(nums) if nums else 0) + 1) if n not in nums]
    low_exp = exp.lower()
    i22, isin, i23 = low_exp.find("2.2"), low_exp.find("co-sinter"), low_exp.find("2.3")
    return {
        "abstract_ok": bool(abs_rows) and abs_rows[0].lower().startswith("high-performance"),
        "intro_ok": bool(intro) and "modular" in intro[0].lower(),
        "exp_ok": 0 <= i22 < isin < i23,
        "no_discussion": all(key != "discussion" for key, _t in practice),
        "chrome_ok": "ARTICLE INFO" not in blob
        and not any("elsevier" in text.lower() for _k, text in practice),
        "ref_missing_n": len(missing),
        "results_under40": sum(1 for text in results if len(text) < 40),
        "practice_n": len(practice),
    }


def fixture_report() -> dict[str, bool]:
    front, pages = elsevier_front_boxes()
    ordered = order_boxes(front, pages)
    text = ordered.marked_text
    exp_boxes, exp_pages = experimental_boxes()
    exp = order_boxes(exp_boxes, exp_pages).marked_text.lower()
    ref_boxes, ref_pages = references_boxes()
    refs = order_boxes(ref_boxes, ref_pages)
    return {
        "role_parse_ok": role_parse_ok([b.role for b in front if b.role]),
        "abstract_before_intro": text.index("High-performance cathode body")
        < text.index("Left introduction"),
        "enum_footer_dropped": "Elsevier" not in text and "Author" not in text,
        "exp_right_top": exp.index("2.2 synthesis") < exp.index("co-sinter") < exp.index("2.3"),
        "refs_not_practice": "[20]" not in "\n".join(body for _k, body in refs.sections)
        and "[20]" in refs.references_text,
    }


def format_fixture_report(report: dict[str, bool]) -> str:
    lines = [f"{key} {str(val)}" for key, val in report.items()]
    lines.append("fixture_ok " + str(all(report.values())))
    return "\n".join(lines) + "\n"


def format_live_report(report: dict[str, Any]) -> str:
    lines = []
    for key in (
        "role_parse_ok",
        "abstract_ok",
        "intro_ok",
        "exp_ok",
        "no_discussion",
        "chrome_ok",
        "ref_missing_n",
        "results_under40",
        "practice_n",
    ):
        if key in report:
            lines.append(f"{key} {report[key]}")
    needed = ("abstract_ok", "intro_ok", "exp_ok", "no_discussion", "chrome_ok")
    live_ok = all(report.get(k) is True for k in needed) and report.get("ref_missing_n") == 0
    lines.append("live_ok " + str(live_ok))
    return "\n".join(lines) + "\n"
