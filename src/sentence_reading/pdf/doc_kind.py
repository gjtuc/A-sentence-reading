"""
design/489 - what kind of document an upload is: paper, peer review file, or a
general document.

A peer review file reprints the paper's title and ships as ESM, so the filename
alone calls it SI. Its head says what it is. A general document (manual, form,
slides) carries none of the signs every paper has somewhere.
"""

from __future__ import annotations

import re
from typing import Literal

DocKind = Literal["paper", "review", "general"]

DOC_KINDS: tuple[str, ...] = ("paper", "review", "general")

_HEAD_CHARS = 12000

_REVIEW_LINE = re.compile(
    r"(?im)^\s*(?:reviewer\s+comments|peer\s+review\s+file|"
    r"response\s+to\s+(?:the\s+)?reviewers?|reviewers'?\s+comments)\b"
)
_REVIEWER_N = re.compile(r"(?i)\breviewer\s*#?\s*(\d)\b")

_HEAD_SIGNS = (
    re.compile(r"(?im)^\s*(?:abstract|a\s?b\s?s\s?t\s?r\s?a\s?c\s?t|summary|초록|요약)\b"),
    re.compile(r"(?im)^\s*(?:\d[\d.]*\s*)?(?:introduction|background|서론)\b"),
    re.compile(r"(?im)^\s*(?:keywords?|key\s+words|주제어)\b"),
    re.compile(r"(?im)^\s*(?:supporting|supplementary)\s+(?:information|materials?|data)\b"),
)
_WHOLE_SIGNS = (
    re.compile(
        r"(?im)^\s*(?:references?|bibliography|literature\s+cited|"
        r"notes\s+and\s+references|참고\s*문헌)\b"
    ),
    re.compile(r"(?i)\b(?:doi\s*[:.]?\s*|doi\.org/)10\.\d{4,9}/"),
    re.compile(r"\bet\s+al\b"),
)


def looks_like_peer_review(text: str) -> bool:
    head = (text or "")[:_HEAD_CHARS]
    if _REVIEW_LINE.search(head):
        return True
    return len({m.group(1) for m in _REVIEWER_N.finditer(head)}) >= 2


def paper_sign_count(text: str) -> int:
    body = text or ""
    head = body[:_HEAD_CHARS]
    return sum(1 for rx in _HEAD_SIGNS if rx.search(head)) + sum(
        1 for rx in _WHOLE_SIGNS if rx.search(body)
    )


def detect_doc_kind(text: str) -> DocKind:
    """Empty text stays a paper: a scan without a text layer is usually one."""
    body = text or ""
    if not body.strip():
        return "paper"
    if looks_like_peer_review(body):
        return "review"
    if paper_sign_count(body) == 0:
        return "general"
    return "paper"


def normalize_doc_kind(raw: object) -> DocKind:
    v = str(raw or "").strip().lower()
    if v in ("review", "general"):
        return v  # type: ignore[return-value]
    return "paper"
