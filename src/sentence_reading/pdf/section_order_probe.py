"""
design/301 — section-order diagnosis without dumping the paper.

Prints marker positions and whether live will replace page text with vision OCR.
Does not call Gemini. Does not print raw page text.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

from sentence_reading.pdf.reading_order import reorder_blocks_two_column

# WHY: Elsevier front page — right column is the abstract sidebar, not body continuation.
DEFAULT_MARKERS: tuple[tuple[str, str], ...] = (
    ("article_info", r"A R T I C L E I N F O"),
    ("abs_banner", r"A B S T R A C T|\bABSTRACT\b"),
    ("keywords", r"\bKeywords?:"),
    ("intro", r"1\.\s*Introduction"),
    ("copyright", r"All rights are reserved"),
)

_SECTION_HEADER = re.compile(
    r"(?i)^(title|abstract|introduction|methods|experimental|results|discussion|"
    r"conclusion|body|supplementary|keywords)\s+(\d+)\s*/\s*(\d+)$"
)
_NAV_NOISE = re.compile(
    r"(?i)^(prev sentence|next sentence|play tts|연습|참고문헌)$"
)


def ascii_head(text: str, n: int = 72) -> str:
    """Windows cp949 consoles raise UnicodeEncodeError on © and similar."""
    t = re.sub(r"\s+", " ", text or "").strip()
    return t.encode("ascii", "replace").decode("ascii")[:n]


def probe_blocks(
    blocks: list[tuple[float, float, float, float, str]],
    *,
    page_width: float,
    markers: tuple[tuple[str, str], ...] | list[tuple[str, str]] | None = None,
) -> dict[str, Any]:
    """Reorder with the same function extract uses, then locate markers."""
    named = list(markers or DEFAULT_MARKERS)
    result = reorder_blocks_two_column(blocks, page_width=page_width)
    hits = _marker_hits(result.text, named)
    by_name = {h["name"]: h for h in hits}
    intro_at = _at(by_name, "intro")
    abs_body_at = _at(by_name, "abs_body")
    copy_at = _at(by_name, "copyright")
    return {
        "multicolumn": result.is_multicolumn,
        "reordered": result.reordered,
        # design/31 — multicolumn pages are forced to vision OCR on the server.
        "vision_repair_expected": result.is_multicolumn,
        "marker_order": [h["name"] for h in hits],
        "markers": hits,
        "intro_before_abstract_body": _before(intro_at, abs_body_at),
        "copyright_before_abstract_body": _before(copy_at, abs_body_at),
    }


def probe_pdf(
    pdf_path: Path,
    *,
    markers: tuple[tuple[str, str], ...] | list[tuple[str, str]] | None = None,
) -> dict[str, Any]:
    """Page-0 block order plus full-text marker positions. No prose dump."""
    import fitz

    from sentence_reading.pdf.extract import extract_text

    named = list(markers or DEFAULT_MARKERS)
    doc = fitz.open(pdf_path)
    try:
        page = doc[0]
        blocks = []
        for block in page.get_text("blocks") or []:
            if len(block) < 5 or not isinstance(block[4], str):
                continue
            text = (block[4] or "").strip()
            if not text:
                continue
            blocks.append(
                (float(block[0]), float(block[1]), float(block[2]), float(block[3]), text)
            )
        width = float(page.rect.width)
        page_count = int(doc.page_count)
    finally:
        doc.close()

    report = probe_blocks(blocks, page_width=width, markers=named)
    report["page_count"] = page_count
    report["page0_blocks"] = len(blocks)
    full = extract_text(pdf_path)
    report["full_marker_order"] = [h["name"] for h in _marker_hits(full, named)]
    report["fallback_sections"] = _fallback_sections(full, named)
    return report


def parse_reader_ui(xml_text: str) -> dict[str, Any]:
    """Flutter reader dump stores labels in content-desc, not text."""
    root = ET.fromstring(xml_text)
    labels: list[str] = []
    section = None
    sentence = ""
    for node in root.iter("node"):
        raw = (node.attrib.get("content-desc") or node.attrib.get("text") or "").strip()
        if not raw:
            continue
        flat = re.sub(r"\s+", " ", raw.replace("\n", " ")).strip()
        labels.append(flat)
        if section is None:
            m = _SECTION_HEADER.match(flat)
            if m:
                section = {
                    "name": m.group(1),
                    "position": int(m.group(2)),
                    "total": int(m.group(3)),
                }
            continue
        # WHY: the app-bar title is a long content-desc before the section chip.
        if sentence or len(flat) < 40 or _NAV_NOISE.match(flat):
            continue
        if flat.lower().startswith(section["name"].lower()):
            continue
        sentence = flat
    return {
        "label_n": len(labels),
        "section": section,
        "sentence_head": ascii_head(sentence),
    }


def format_report(report: dict[str, Any], ui: dict[str, Any] | None = None) -> str:
    lines = [
        f"page0_multicolumn {report.get('multicolumn')}",
        f"vision_repair_expected {report.get('vision_repair_expected')}",
        "path_note pymupdf_order_is_not_live_tags_when_vision_repair_expected",
        "marker_order " + " ".join(report.get("marker_order") or []),
        f"intro_before_abstract_body {report.get('intro_before_abstract_body')}",
        f"copyright_before_abstract_body {report.get('copyright_before_abstract_body')}",
    ]
    if report.get("full_marker_order"):
        lines.append("full_marker_order " + " ".join(report["full_marker_order"]))
    for row in report.get("fallback_sections") or []:
        lines.append(
            "fallback {name} chunk {chunk} section {section}".format(**row)
        )
    if ui is not None:
        sec = ui.get("section") or {}
        if sec:
            lines.append(
                "ui_section {name} {position}/{total}".format(
                    name=sec.get("name"),
                    position=sec.get("position"),
                    total=sec.get("total"),
                )
            )
        else:
            lines.append("ui_section missing")
        lines.append("ui_sentence_head " + ascii_head(str(ui.get("sentence_head") or "")))
        lines.append(f"ui_label_n {ui.get('label_n')}")
    text = "\n".join(lines) + "\n"
    return text.encode("ascii", "replace").decode("ascii")


def _marker_hits(text: str, markers: list[tuple[str, str]]) -> list[dict[str, Any]]:
    hits: list[dict[str, Any]] = []
    for name, pat in markers:
        m = re.search(pat, text or "")
        if not m:
            continue
        hits.append({"name": name, "at": m.start()})
    hits.sort(key=lambda h: h["at"])
    return hits


def _at(by_name: dict[str, dict[str, Any]], name: str) -> int | None:
    row = by_name.get(name)
    if not row:
        return None
    return int(row["at"])


def _before(a: int | None, b: int | None) -> bool | None:
    if a is None or b is None:
        return None
    return a < b


def _fallback_sections(text: str, markers: list[tuple[str, str]]) -> list[dict[str, Any]]:
    from sentence_reading.llm.debone import chunk_raw_text
    from sentence_reading.llm.debone_quality import infer_section_for_chunk

    class _Ctx:
        section_order = [
            "title",
            "abstract",
            "introduction",
            "methods",
            "results",
            "discussion",
            "conclusion",
        ]

    chunks = chunk_raw_text(text)
    if not chunks:
        return []
    out: list[dict[str, Any]] = []
    pos = 0
    spans: list[tuple[int, int, int]] = []
    for i, chunk in enumerate(chunks):
        spans.append((pos, pos + len(chunk), i))
        pos += len(chunk) + 2
    for hit in _marker_hits(text, markers):
        chunk_i = 0
        for start, end, i in spans:
            if start <= hit["at"] < end:
                chunk_i = i
                break
        out.append(
            {
                "name": hit["name"],
                "chunk": chunk_i,
                "section": infer_section_for_chunk(chunk_i, len(chunks), _Ctx()),
            }
        )
    return out
