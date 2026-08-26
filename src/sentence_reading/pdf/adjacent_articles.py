"""
design/136 — keep first article only when a PDF concatenates several papers.

WHY: issue-style / merged PDFs mix foreign sentences & figures into the library.
Fail-closed: multi-article signals without a clean cut → refuse ingest (no silent whole-file success).
"""

from __future__ import annotations

import os
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path

from sentence_reading.pdf.extract import (
    _COVER_DOI,
    page_text_looks_like_title_cover,
)

# Min gap between article starts (skip abstract/TOC twins on the next page).
_MIN_START_GAP = 3
# Front-matter window — citations in References must not count as a new DOI.
_FRONT_CHARS = 900
_ARXIV_ID = re.compile(r"\barxiv:\s*\d{4}\.\d{4,5}(?:v\d+)?\b", re.IGNORECASE)
_REFS_HEAD = re.compile(r"^\s*references\b", re.IGNORECASE | re.MULTILINE)
_CITE_BRACKET = re.compile(r"\[\d{1,3}\]")
_ABSTRACT_HEAD = re.compile(r"\babstract\b", re.IGNORECASE)
_CITE_LINE = re.compile(r"^\s*\[\d{1,3}\]\s+\S", re.MULTILINE)


class AdjacentArticlesError(ValueError):
    """User-facing ingest refusal when adjacent papers cannot be cut safely."""


def strip_adjacent_enabled() -> bool:
    """Kill switch: ASR_STRIP_ADJACENT=0 restores whole-PDF ingest."""
    v = (os.environ.get("ASR_STRIP_ADJACENT") or "1").strip().lower()
    return v not in ("0", "false", "off", "no")


def _front_matter_slice(text: str) -> str:
    """Text before a References section — avoids bibliography DOIs/titles."""
    raw = (text or "").replace("\x00", "")
    m = re.search(r"\n\s*References\s*\n", raw[:3000], re.IGNORECASE)
    if m:
        raw = raw[: m.start()]
    return raw


def _looks_like_references_page(text: str) -> bool:
    """Reject citation/refs pages so bibliography titles are not new articles."""
    raw = (text or "").replace("\x00", "")
    head = raw[:500]
    if _REFS_HEAD.search(head):
        return True
    # EDGE: Acknowledgements then References on same page (end of paper A).
    if re.search(r"\breferences\b", raw[:2200], re.IGNORECASE) and (
        len(_CITE_LINE.findall(raw[:3500])) >= 2
        or len(_CITE_BRACKET.findall(raw[:2500])) >= 6
    ):
        return True
    # EDGE: numbered bibliography lines `[16] Author…`
    if len(_CITE_LINE.findall(raw[:3500])) >= 3:
        return True
    if len(_CITE_BRACKET.findall(raw[:2500])) >= 8:
        if not _ABSTRACT_HEAD.search(raw[:500]):
            return True
    return False


def _front_ids(text: str) -> set[str]:
    """DOI / arXiv ids from page front matter only (not deep reference lists)."""
    front = _front_matter_slice(text)[:_FRONT_CHARS]
    ids = {m.group(0).lower() for m in _COVER_DOI.finditer(front)}
    ids |= {m.group(0).lower().replace(" ", "") for m in _ARXIV_ID.finditer(front)}
    return ids


def _looks_like_article_start(text: str) -> bool:
    """Front matter for a new article — stricter than cover alone mid-PDF.

    WHY: figure captions / acknowledgement pages can trip the cover heuristic;
    secondary starts need Abstract / corresponding author / affil+DOI as well.
    """
    if _looks_like_references_page(text):
        return False
    matter = _front_matter_slice(text)
    head = matter[:700]
    has_abs = bool(_ABSTRACT_HEAD.search(head))
    # Do NOT use Correspond\w* alone — "corresponding to" in figure captions matches.
    has_corresp = bool(
        re.search(
            r"\bCorrespondence\b|\bCorresponding\s+authors?\b|\bCorrespondencia\b|"
            r"\bE-?mails?\b|\bAuthors?\s+for\s+correspondence\b",
            matter[:2000],
            re.IGNORECASE,
        )
    )
    has_affil = bool(
        re.search(
            r"\b(University|Department|Institute|Laboratory|College|"
            r"Departamento|Universidad)\b",
            matter[:2000],
            re.IGNORECASE,
        )
    )
    has_doi = bool(_front_ids(text))
    email_n = matter[:2000].count("@")
    if page_text_looks_like_title_cover(text):
        if has_abs or has_corresp or (has_affil and has_doi):
            return True
        if has_affil and has_abs:
            return True
        # Journal communication first page: dept + author emails, abstract below.
        if has_affil and email_n >= 1:
            return True
        if has_affil and re.search(r"\b(Abstract|Resumen)\b", head, re.IGNORECASE):
            return True
        return False
    if has_abs and has_doi:
        return True
    return False


def find_article_start_pages(page_texts: list[str]) -> list[int]:
    """Return 0-based page indices that look like article front matter.

    Page 0 is always a start when the PDF is non-empty (first article).
    """
    if not page_texts:
        return []
    starts = [0]
    last = 0
    for i in range(1, len(page_texts)):
        if i - last < _MIN_START_GAP:
            continue
        text = page_texts[i] or ""
        if not _looks_like_article_start(text):
            continue
        starts.append(i)
        last = i
    return starts


def multi_article_ids_without_cut(page_texts: list[str], starts: list[int]) -> bool:
    """True when ≥2 distinct front-matter ids exist but we lack a second start.

    WHY (product 3B): do not pretend a multi-paper PDF is one paper.
    Only count ids on pages that look like starts (or page 0) to avoid
    reference-list DOIs creating false multi signals.
    """
    if len(starts) >= 2:
        return False
    seen: set[str] = set()
    for i, text in enumerate(page_texts):
        if i != 0 and not _looks_like_article_start(text):
            continue
        seen |= _front_ids(text)
        if len(seen) >= 2:
            return True
    return False


@dataclass(frozen=True)
class TrimPlan:
    starts: list[int]
    keep_end_exclusive: int | None  # None = keep all pages
    trimmed: bool
    reason: str


def plan_first_article(page_texts: list[str]) -> TrimPlan:
    """Decide keep range or raise AdjacentArticlesError."""
    n = len(page_texts)
    if n == 0:
        raise AdjacentArticlesError("빈 PDF는 처리할 수 없습니다.")
    starts = find_article_start_pages(page_texts)
    if multi_article_ids_without_cut(page_texts, starts):
        # Fail-closed: foreign paper signals without a safe boundary.
        raise AdjacentArticlesError(
            "여러 논문이 한 파일에 있는 것 같지만 경계를 찾지 못했습니다. "
            "논문 하나만 있는 PDF로 다시 올려 주세요."
        )
    if len(starts) >= 2:
        end = starts[1]
        if end <= starts[0] or end > n:
            raise AdjacentArticlesError(
                "여러 논문이 한 파일에 있는 것 같지만 경계를 찾지 못했습니다. "
                "논문 하나만 있는 PDF로 다시 올려 주세요."
            )
        return TrimPlan(
            starts=starts,
            keep_end_exclusive=end,
            trimmed=True,
            reason="first_article_only",
        )
    return TrimPlan(
        starts=starts,
        keep_end_exclusive=None,
        trimmed=False,
        reason="single_article",
    )


def prepare_pdf_first_article(pdf_path: Path) -> tuple[Path, TrimPlan]:
    """Return (path_to_use, plan). May write a trimmed temp PDF beside the original.

    When disabled via kill switch, returns the original path unchanged.
    """
    if not strip_adjacent_enabled():
        return pdf_path, TrimPlan(starts=[0], keep_end_exclusive=None, trimmed=False, reason="kill_off")

    import fitz

    doc = fitz.open(pdf_path)
    try:
        if doc.is_encrypted:
            raise ValueError("encrypted_pdf")
        texts = []
        for page in doc:
            try:
                texts.append(page.get_text("text") or "")
            except Exception:
                texts.append("")
        plan = plan_first_article(texts)
        if not plan.trimmed or plan.keep_end_exclusive is None:
            return pdf_path, plan
        end = plan.keep_end_exclusive
        # WHY: write a new file — ingest still owns tmp lifecycle / unlink.
        out = Path(
            tempfile.NamedTemporaryFile(
                prefix="asr_adj_",
                suffix=".pdf",
                delete=False,
            ).name
        )
        trimmed = fitz.open()
        try:
            trimmed.insert_pdf(doc, from_page=0, to_page=end - 1)
            trimmed.save(out)
        finally:
            trimmed.close()
        return out, plan
    finally:
        doc.close()
