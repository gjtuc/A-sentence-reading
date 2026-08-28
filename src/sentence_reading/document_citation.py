"""
무엇을: ingest 시 이 논문 bibliographic 한 줄 + DOI 추출 (design/157).
왜: Title 섹션 "이 논문" 패널 — References [n]과 별도 고정 행.
"""

from __future__ import annotations

import re
from typing import Any

from sentence_reading.cite_refs import extract_doi, strip_tags
from sentence_reading.pdf.adjacent_articles import _front_matter_slice

_FRONT_CHARS = 1200
_MAX_TEXT = 500
_DOI_ALL = re.compile(
    r"\b(?:doi[:\s]*)?(10\.\d{4,9}/[-._;()/:A-Z0-9]+)\b",
    re.IGNORECASE,
)


def _plain(s: str) -> str:
    t = strip_tags(s or "")
    return re.sub(r"\s+", " ", t).strip()


def _all_dois(text: str) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for m in _DOI_ALL.finditer(text or ""):
        doi = m.group(1).rstrip(").,;")
        key = doi.lower()
        if key not in seen:
            seen.add(key)
            out.append(doi)
    return out


def _front_blob(
    full_text: str,
    pdf_pages: list[str] | None,
) -> str:
    if pdf_pages:
        parts = [_plain(p) for p in pdf_pages[:2] if _plain(p)]
        if parts:
            return "\n".join(parts)[:_FRONT_CHARS]
    return _front_matter_slice(full_text or "")[:_FRONT_CHARS]


def _line_with_doi(blob: str, doi: str) -> str:
    if not blob or not doi:
        return ""
    low = doi.lower()
    for ln in blob.splitlines():
        pl = _plain(ln)
        if low in pl.lower() and len(pl) >= 8:
            return pl[:_MAX_TEXT]
    return ""


def _pack(
    *,
    text: str,
    doi: str = "",
    source: str,
    confidence: str,
) -> dict[str, Any]:
    plain = _plain(text)
    if len(plain) < 3:
        return {}
    d = (doi or "").strip() or (extract_doi(plain) or "")
    return {
        "text": plain[:_MAX_TEXT],
        "doi": d,
        "source": source,
        "confidence": confidence,
    }


def public_document_citation(raw: object) -> dict[str, Any]:
    """API/캐시용 — 빈/쓰레기 입력은 {}."""
    if not isinstance(raw, dict):
        return {}
    text = _plain(str(raw.get("text") or ""))
    if len(text) < 3:
        return {}
    doi = str(raw.get("doi") or "").strip() or (extract_doi(text) or "")
    source = str(raw.get("source") or "").strip()[:40]
    confidence = str(raw.get("confidence") or "").strip()[:10]
    out: dict[str, Any] = {"text": text[:_MAX_TEXT], "doi": doi}
    if source:
        out["source"] = source
    if confidence:
        out["confidence"] = confidence
    return out


def extract_document_citation(
    *,
    full_text: str,
    pdf_pages: list[str] | None,
    title: str,
    title_section_sentences: list[str] | None = None,
) -> dict[str, Any]:
    """
    이 논문 한 줄 메타. 실패 시 {}.
    우선순위: front matter DOI → title 섹션 DOI → title_only.
    """
    title_plain = _plain(title)
    title_blob = "\n".join(_plain(s) for s in (title_section_sentences or []) if _plain(s))

    front = _front_blob(full_text, pdf_pages)
    front_dois = _all_dois(front)

    if front_dois:
        doi = front_dois[0]
        conf = "high" if len(front_dois) == 1 else "low"
        line = _line_with_doi(front, doi)
        text = line or title_plain or doi
        if title_plain and title_plain.lower() not in text.lower():
            text = f"{title_plain}. {line or f'doi:{doi}'}"[:_MAX_TEXT]
        return _pack(text=text, doi=doi, source="front_matter", confidence=conf)

    if title_blob:
        td = extract_doi(title_blob)
        if td:
            line = _line_with_doi(title_blob, td)
            text = line or title_plain or title_blob
            return _pack(text=text, doi=td, source="title_sentences", confidence="high")

    if len(title_plain) >= 10:
        return _pack(
            text=title_plain,
            doi="",
            source="title_only",
            confidence="low",
        )
    return {}
