"""
design/152 · 222 · 229 — SI vs main from document head text (+ densified detect).
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Literal

DocRole = Literal["main", "supplementary"]

_HEAD_CHARS = 8000

# Journal SI cover lines (first pages).
_SI_HEAD = re.compile(
    r"(?im)"
    r"(?:^|\n)\s*("
    r"supplementary\s+(?:information|materials?|data)"
    r"|supporting\s+information"
    r"|electronic\s+supplementary"
    r"|esi\b"
    r")"
)

# Filename hints (ACS …_si_001.pdf). Never sole authority without content signal.
_SI_FILENAME = re.compile(
    r"(?i)(?:^|[/\_.-])si(?:[_.=-]|\d)|supporting[-_ ]?information|suppl(?:ementary)?"
)

# Page label "S-1" / "S1" near head (common SI cover).
_SI_PAGE_LABEL = re.compile(r"(?im)(?:^|\n)\s*S\s*[-–—]?\s*\d{1,3}\b")

# design/229 — ACS article chrome near a Supporting Information *badge* (not SI cover).
_ACS_CHROME = (
    re.compile(r"(?im)(?:^|\n)\s*ACCESS\b"),
    re.compile(r"(?im)Metrics\s*&\s*More"),
    re.compile(r"(?im)Article\s+Recommendations"),
    # ACS extracts often use Latin small letter dotless i (U+0131).
    re.compile(r"(?im)(?:^|\n)\s*s[iı]\b"),
)

_ABSTRACT_SOON = re.compile(r"(?im)(?:ABSTRACT\s*:|(?:^|\n)\s*ABSTRACT\b)")

# Strip BOM / bidi / zero-width before matching (ZWSP was failing live SI heads).
_FORMAT_CF = {"Cf", "Cc"}


@dataclass(frozen=True)
class DocRoleDetectResult:
    role: DocRole
    reason: str
    head_len: int
    marker_hit: bool
    filename_si_hint: bool
    page_label_hit: bool
    stripped_format: bool
    override: bool = False


def _strip_format_chars(text: str) -> tuple[str, bool]:
    raw = text or ""
    out: list[str] = []
    stripped = False
    for ch in raw:
        if ch in ("\n", "\r", "\t"):
            out.append(ch)
            continue
        cat = unicodedata.category(ch)
        if cat in _FORMAT_CF or ch in ("\ufeff", "\u200b", "\u200c", "\u200d", "\u2060"):
            stripped = True
            continue
        out.append(ch)
    return "".join(out), stripped


def filename_looks_like_si(filename: str | None) -> bool:
    name = (filename or "").strip()
    if not name:
        return False
    base = name.rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
    return bool(_SI_FILENAME.search(base))


def _is_acs_main_si_badge(head: str, match: re.Match[str]) -> bool:
    """True when SI phrase is an ACS main-article badge, not an SI cover."""
    start = max(0, match.start() - 400)
    end = min(len(head), match.end() + 250)
    window = head[start:end]
    chrome_hits = sum(1 for pat in _ACS_CHROME if pat.search(window))
    after = head[match.end() : match.end() + 300]
    abstract_soon = bool(_ABSTRACT_SOON.search(after))
    return chrome_hits >= 2 and abstract_soon


def detect_doc_role_detailed(
    text: str,
    *,
    filename: str | None = None,
    override: str | None = None,
) -> DocRoleDetectResult:
    """Classify doc role with explicit reason for evidence (design/222 · 229)."""
    if (override or "").strip():
        role = normalize_doc_role(override)
        return DocRoleDetectResult(
            role=role,
            reason="job_override",
            head_len=0,
            marker_hit=False,
            filename_si_hint=filename_looks_like_si(filename),
            page_label_hit=False,
            stripped_format=False,
            override=True,
        )

    cleaned, stripped = _strip_format_chars(text or "")
    head = cleaned[:_HEAD_CHARS]
    head_len = len(head)
    fn_hint = filename_looks_like_si(filename)
    page_label = bool(_SI_PAGE_LABEL.search(head[:1200])) if head_len else False
    marker_m = _SI_HEAD.search(head) if head_len else None

    if not head.strip():
        # EDGE: empty extract — filename alone is too weak (main PDFs named *_si by mistake).
        return DocRoleDetectResult(
            role="main",
            reason="empty_head",
            head_len=0,
            marker_hit=False,
            filename_si_hint=fn_hint,
            page_label_hit=False,
            stripped_format=stripped,
        )

    if marker_m is not None:
        if _is_acs_main_si_badge(head, marker_m):
            return DocRoleDetectResult(
                role="main",
                reason="head_marker_acs_chrome_veto",
                head_len=head_len,
                marker_hit=True,
                filename_si_hint=fn_hint,
                page_label_hit=page_label,
                stripped_format=stripped,
            )
        return DocRoleDetectResult(
            role="supplementary",
            reason="head_marker",
            head_len=head_len,
            marker_hit=True,
            filename_si_hint=fn_hint,
            page_label_hit=page_label,
            stripped_format=stripped,
        )

    # Secondary: ACS-style filename + S-n page label near cover (no journal SI phrase).
    if fn_hint and page_label:
        return DocRoleDetectResult(
            role="supplementary",
            reason="filename_si_and_page_label",
            head_len=head_len,
            marker_hit=False,
            filename_si_hint=True,
            page_label_hit=True,
            stripped_format=stripped,
        )

    return DocRoleDetectResult(
        role="main",
        reason="default_main",
        head_len=head_len,
        marker_hit=False,
        filename_si_hint=fn_hint,
        page_label_hit=page_label,
        stripped_format=stripped,
    )


def detect_doc_role(text: str, *, filename: str | None = None) -> DocRole:
    """Return supplementary when SI marker appears in the document head."""
    return detect_doc_role_detailed(text, filename=filename).role


def normalize_doc_role(raw: str | None) -> DocRole:
    v = (raw or "").strip().lower()
    if v in ("supplementary", "si", "supp"):
        return "supplementary"
    if v in ("merged", "main+supplementary", "main_supplementary"):
        return "main"  # merged is index-only; ingest always main|supplementary
    return "main"
