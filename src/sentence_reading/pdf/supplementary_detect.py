"""
design/152 · 222 · 229 · 235 · 363 — SI vs main.

design/363 — two signals, either is enough. A cover phrase *above the title*,
or an SI token in the filename. A mention of supplementary material in the body
is not a cover: main papers print that after the title, and it is very hard for
them to print it above.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Literal

DocRole = Literal["main", "supplementary"]

_HEAD_CHARS = 8000

# design/363 — the cover line, and only as its own line. A sentence that merely
# mentions Supporting Information does not match.
_COVER_LINE = re.compile(
    r"(?i)^\s*(?:the\s+)?("
    r"supporting\s+information"
    r"|supporting\s+online\s+materials?"
    r"|supporting\s+materials?"
    r"|supplementary\s+information"
    r"|supplementary\s+materials?"
    r"|electronic\s+supplementary\s+information"
    r")\b"
)

# Leading journal furniture. Skipped when looking for the cover line and the title.
_CHROME_LINE = re.compile(
    r"(?i)^\s*("
    r"s\s*[-–—]?\s*\d{1,3}"
    r"|access"
    r"|metrics\s*&\s*more"
    r"|article\s+recommendations"
    r"|read\s+online"
    r"|cite\s+this\s*:"
    r"|article"
    r"|research"
    r"|https?://\S+"
    r"|doi:\s*\S+"
    r"|www\.\S+"
    r"|in\s+the\s+format\s+provided\s+by\s+the"
    r"|authors\s+and\s+unedited"
    r")\s*$"
)
_ABSTRACT_LINE = re.compile(r"(?i)^\s*(abstract|conspectus)\b")

# Filename hints (ACS …_si_001.pdf, Elsevier mmc1, Wiley suppmat).
# design/281 — do NOT match bare "sup"/"supp" inside "supported"/"support".
_SI_FILENAME = re.compile(
    r"(?i)(?:^|[/\_.-])(?:"
    r"si(?:[_.=-]|\d|$)"
    r"|mmc\d+"
    r"|moesm\d*"
    r"|esm\d+"
    r"|supp?(?:mat|l(?:ementary)?)(?:[-_.]?\d+)?"
    r"|sup[-_.]?\d+"
    r")"
    r"|supporting[-_ ]?information"
    r"|suppl(?:ementary)?"
    r"|[-_.]som(?:[-_.]|$)"
)

# Page label "S-1" / "S1" near head (common SI cover).
_SI_PAGE_LABEL = re.compile(r"(?im)(?:^|\n)\s*S\s*[-–—]?\s*\d{1,3}\b")


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


def _is_chrome_line(line: str) -> bool:
    s = (line or "").strip()
    if not s:
        return True
    if len(s) <= 2:
        return True
    if _CHROME_LINE.match(s):
        return True
    # ACS extracts a lone "sı" / "si" badge next to ACCESS.
    if re.fullmatch(r"(?i)s[iı]", s):
        return True
    # "Cite This: ACS Catal. 2022, 12, 8352" — the rest of the line is the journal.
    if re.match(r"(?i)^cite\s+this\b", s):
        return True
    return False


def cover_phrase_above_title(text: str) -> bool:
    """True when a cover phrase is printed before the paper's title (design/363).

    Walk the head from the top. Skip journal furniture. The first real line is
    either the cover (`Supporting Information` then the title) or the title
    itself (the cover, if any, is then a badge above the abstract). A cover
    line sitting on top of `ABSTRACT` with no title in between is that badge.
    """
    cover_seen = False
    for raw in (text or "").splitlines():
        if _is_chrome_line(raw):
            continue
        if _COVER_LINE.match(raw):
            cover_seen = True
            continue
        if _ABSTRACT_LINE.match(raw):
            return False
        return cover_seen
    return cover_seen


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
    cover_hit = cover_phrase_above_title(head) if head_len else False

    if not head.strip():
        # design/280 — Info.Title may still yield a title while extract text is empty.
        if fn_hint:
            return DocRoleDetectResult(
                role="supplementary",
                reason="filename_si",
                head_len=0,
                marker_hit=False,
                filename_si_hint=True,
                page_label_hit=False,
                stripped_format=stripped,
            )
        return DocRoleDetectResult(
            role="main",
            reason="empty_head",
            head_len=0,
            marker_hit=False,
            filename_si_hint=fn_hint,
            page_label_hit=False,
            stripped_format=stripped,
        )

    # design/363 — either signal is enough. Filename first so a Nature SI whose
    # cover line sits under the reprinted title is still SI.
    if fn_hint:
        return DocRoleDetectResult(
            role="supplementary",
            reason="filename_si",
            head_len=head_len,
            marker_hit=cover_hit,
            filename_si_hint=True,
            page_label_hit=page_label,
            stripped_format=stripped,
        )
    if cover_hit:
        return DocRoleDetectResult(
            role="supplementary",
            reason="cover_above_title",
            head_len=head_len,
            marker_hit=True,
            filename_si_hint=False,
            page_label_hit=page_label,
            stripped_format=stripped,
        )

    return DocRoleDetectResult(
        role="main",
        reason="default_main",
        head_len=head_len,
        marker_hit=False,
        filename_si_hint=False,
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
