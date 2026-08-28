"""
design/152 — SI vs main from document head text.
"""

from __future__ import annotations

import re
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


def detect_doc_role(text: str) -> DocRole:
    """Return supplementary when SI marker appears in the document head."""
    head = (text or "")[:_HEAD_CHARS]
    if not head.strip():
        return "main"
    if _SI_HEAD.search(head):
        return "supplementary"
    return "main"


def normalize_doc_role(raw: str | None) -> DocRole:
    v = (raw or "").strip().lower()
    if v in ("supplementary", "si", "supp"):
        return "supplementary"
    if v in ("merged", "main+supplementary", "main_supplementary"):
        return "main"  # merged is index-only; ingest always main|supplementary
    return "main"
