"""
무엇을: 본문 각주 번호 ↔ References 항목 매칭 · DOI 문자열 추출 (design/41).
왜: Fig. 점프(28)와 같이 힌트만 — 원문 열기는 Crossref/DOI 층.
다음에: 이름-연도 인용 · 출판사별 검색 URL.
"""

from __future__ import annotations

import re
from typing import Any

_TAG = re.compile(r"<[^>]+>")
# WHY: DOI는 대소문자·접두 섞임 — Crossref/doi.org 공통
_DOI = re.compile(
    r"\b(?:doi[:\s]*)?(10\.\d{4,9}/[-._;()/:A-Z0-9]+)\b",
    re.IGNORECASE,
)
# [1] [1-3] [1,2] [1–3]
_BRACKET = re.compile(
    r"\[(\d+(?:\s*[-–—,]\s*\d+)*(?:\s*,\s*\d+(?:\s*[-–—,]\s*\d+)*)*)\]"
)
# <sup>12</sup> — 숫자만 (cm<sup>−1</sup> 등은 제외)
_SUP_NUM = re.compile(r"<sup>\s*(\d{1,3})\s*</sup>", re.IGNORECASE)
# Bracket cite shape — survey glossary가 [8, 9]를 LaTeX $1로 바꾸는 사고 방어
_CITE_BRACKET_RAW = re.compile(
    r"^\[\s*\d+(?:\s*[-–—,]\s*\d+)*\s*\]$"
)
# Word-attached $n (dioxide$1) — glossary 오염·TeX 각주 잔재; $33.00(앞 공백)은 제외
_DOLLAR_CITE = re.compile(r"(?<=[A-Za-z)\]])\$(\d{1,3})(?!\d)")
# [8, 9]$1 · </sub>$1 — ] 또는 HTML 닫는 태그 직후 $n (Co–TiO₂ hybrid cite QA)
_DOLLAR_CITE_AFTER_MARK = re.compile(r"([\]>])\s*\$(\d{1,3})(?!\d)")
# $^{8,9}$ / ${^8,9}$ — LaTeX 각주
_DOLLAR_TEX_CITE = re.compile(
    r"\$\{\^(\d+(?:\s*[,–—−-]\s*\d+)*)\}\$|\$\^\{(\d+(?:\s*[,–—−-]\s*\d+)*)\}\$",
    re.IGNORECASE,
)
# ACS plain trailing cite — reaction.6−9 · worldwide.1−5 (design/0.3.93)
_PLAIN_TRAILING = re.compile(
    r"(?<=[a-zA-Z\)])(\.(\d+(?:\s*[-–—−,]\s*\d+)*))\s*$"
)
# References 섹션 헤더
_REF_HEAD = re.compile(
    r"(?im)^(?:\s*)(references|bibliography|literature cited)\s*$"
)
# 번호 매긴 항목 시작: 1.  1)  [1]  1·
_ENTRY_START = re.compile(
    r"(?m)^\s*(?:\[(\d+)\]|(\d+)\s*[\.\)\]])\s+"
)


def strip_tags(html: str) -> str:
    return _TAG.sub(" ", html or "")


def looks_like_citation_glossary_raw(raw: str) -> bool:
    """Survey formulas에 각주 [n] / [n,m]가 들어가면 apply_glossary 스킵."""
    return bool(_CITE_BRACKET_RAW.match((raw or "").strip()))


def glossary_rich_is_allowed(rich: str) -> bool:
    """Survey rich는 <sub>/<sup>/<i>/<em>만 — LaTeX $…$ 거부."""
    r = (rich or "").strip()
    if not r or "$" in r:
        return False
    plain = strip_tags(r)
    if "<" in r:
        # 허용 태그 외 HTML/속성 거부
        for m in re.finditer(r"</?([a-zA-Z0-9]+)", r):
            if m.group(1).lower() not in ("sub", "sup", "i", "em"):
                return False
    return bool(plain)


def _expand_dollar_token(token: str) -> list[int]:
    return _expand_num_token(token.replace(" ", ""))


def _parse_dollar_cite_numbers(text: str) -> list[int]:
    out: list[int] = []
    seen: set[int] = set()

    def _add(nums: list[int]) -> None:
        for n in nums:
            if n not in seen:
                seen.add(n)
                out.append(n)

    for m in _DOLLAR_TEX_CITE.finditer(text or ""):
        inner = m.group(1) or m.group(2) or ""
        _add(_expand_dollar_token(inner))
    for m in _DOLLAR_CITE_AFTER_MARK.finditer(text or ""):
        _add([int(m.group(2))])
    for m in _DOLLAR_CITE.finditer(text or ""):
        _add([int(m.group(1))])
    return out


def _sub_dollar_cite_artifacts(s: str) -> str:
    """LaTeX·word-attached·]/> 뒤 $n 제거 — repair/strip 공용."""

    def _tex(m: re.Match[str]) -> str:
        inner = m.group(1) or m.group(2) or ""
        return "" if _expand_dollar_token(inner) else m.group(0)

    def _dollar(m: re.Match[str]) -> str:
        n = int(m.group(1))
        return "" if 1 <= n <= 999 else m.group(0)

    def _after_mark(m: re.Match[str]) -> str:
        n = int(m.group(2))
        return m.group(1) if 1 <= n <= 999 else m.group(0)

    s = _DOLLAR_TEX_CITE.sub(_tex, s)
    s = _DOLLAR_CITE_AFTER_MARK.sub(_after_mark, s)
    return _DOLLAR_CITE.sub(_dollar, s)


def repair_dollar_cite_artifacts(text: str) -> str:
    """
    Ingest — glossary가 [8, 9]→$1로 바꾼 뒤 남는 word-attached $n 제거.
    WHY: 재분석 전 캐시·표시층 모두에서 cite 흔적($1) 정리; 가격($33)은 유지.
    """
    return _sub_dollar_cite_artifacts(text or "")


def extract_doi(text: str) -> str | None:
    """문헌 문자열에 DOI가 있으면 정규화해 반환."""
    if not text:
        return None
    m = _DOI.search(text)
    if not m:
        return None
    doi = m.group(1).rstrip(").,;")
    return doi


def _expand_num_token(token: str) -> list[int]:
    """'1-3,5' → [1,2,3,5]. 말도 안 되는 범위는 스킵."""
    out: list[int] = []
    seen: set[int] = set()
    for part in re.split(r"\s*,\s*", token.strip()):
        part = part.strip()
        if not part:
            continue
        m = re.match(r"^(\d+)\s*[-–—−]\s*(\d+)$", part)
        if m:
            a, b = int(m.group(1)), int(m.group(2))
            if a > b or b - a > 40:
                # WHY: OCR 쓰레기 범위 방어
                continue
            for n in range(a, b + 1):
                if n not in seen and 1 <= n <= 9999:
                    seen.add(n)
                    out.append(n)
            continue
        if part.isdigit():
            n = int(part)
            if n not in seen and 1 <= n <= 9999:
                seen.add(n)
                out.append(n)
    return out


def _parse_plain_trailing_cite_numbers(text: str) -> list[int]:
    m = _PLAIN_TRAILING.search(text or "")
    if not m:
        return []
    return _expand_num_token(m.group(2))


def parse_cite_numbers(text: str) -> list[int]:
    """문장에서 각주 번호 목록 (등장 순 · 중복 제거)."""
    raw = text or ""
    out: list[int] = []
    seen: set[int] = set()

    def _add(nums: list[int]) -> None:
        for n in nums:
            if n not in seen:
                seen.add(n)
                out.append(n)

    for m in _BRACKET.finditer(strip_tags(raw)):
        _add(_expand_num_token(m.group(1)))
    for m in _SUP_NUM.finditer(raw):
        _add([int(m.group(1))])
    for n in _parse_dollar_cite_numbers(raw):
        _add([n])
    _add(_parse_plain_trailing_cite_numbers(strip_tags(raw)))
    return out


def strip_cite_markers_for_display(html: str) -> str:
    """
    문장 박스 표시용 — 유효 각주 마커만 제거 (design/49).
    칩 매칭은 원문 유지. JS `stripCiteMarkersForDisplay` 와 동기.
    """
    s = html or ""

    def _sup(m: re.Match[str]) -> str:
        n = int(m.group(1))
        return "" if 1 <= n <= 999 else m.group(0)

    s = _SUP_NUM.sub(_sup, s)
    # WHY: $n 을 브래킷보다 먼저 — [8, 9]$1 → $1 제거 후 [8,9] 제거 (design/49 hybrid)
    s = _sub_dollar_cite_artifacts(s)

    def _br(m: re.Match[str]) -> str:
        return "" if _expand_num_token(m.group(1)) else m.group(0)

    s = _BRACKET.sub(_br, s)

    def _plain_trailing(m: re.Match[str]) -> str:
        return "." if _expand_num_token(m.group(2)) else m.group(0)

    s = _PLAIN_TRAILING.sub(_plain_trailing, s)
    s = re.sub(r"\s+([.,;:!?)])", r"\1", s)
    s = re.sub(r"\s{2,}", " ", s)
    return s.strip()


def extract_bibliography(full_text: str) -> list[dict[str, Any]]:
    """
    원문에서 References 블록 → [{n, text, doi}].
    헤더 없으면 빈 목록 (fail-soft).
    """
    text = full_text or ""
    if not text.strip():
        return []

    # 헤더 위치
    head = _REF_HEAD.search(text)
    if not head:
        # 본문 중간의 'References\n' 변형
        loose = re.search(
            r"(?is)\n\s*(references|bibliography)\s*\n",
            text,
        )
        if not loose:
            return []
        start = loose.end()
    else:
        start = head.end()

    body = text[start:]
    # 다음 큰 섹션(부록 등)에서 자르기 — 관대
    cut = re.search(
        r"(?im)^\s*(appendix|supporting information|acknowledg(?:e)?ments?)\s*$",
        body,
    )
    if cut:
        body = body[: cut.start()]

    entries: list[dict[str, Any]] = []
    matches = list(_ENTRY_START.finditer(body))
    if not matches:
        return []

    for i, m in enumerate(matches):
        n_s = m.group(1) or m.group(2)
        try:
            n = int(n_s)
        except (TypeError, ValueError):
            continue
        if not (1 <= n <= 9999):
            continue
        end = matches[i + 1].start() if i + 1 < len(matches) else len(body)
        chunk = body[m.end() : end]
        # 공백 정리
        plain = re.sub(r"\s+", " ", chunk).strip(" \t\r\n.;")
        if len(plain) < 8:
            continue
        if len(plain) > 2000:
            plain = plain[:2000]
        doi = extract_doi(plain) or ""
        entries.append({"n": n, "text": plain, "doi": doi})

    # 같은 n 이 여러 번이면 첫 것만
    by_n: dict[int, dict[str, Any]] = {}
    for e in entries:
        by_n.setdefault(int(e["n"]), e)
    return [by_n[k] for k in sorted(by_n)]


def lookup_reference(
    n: int,
    bibliography: list[dict[str, Any]] | None,
) -> dict[str, Any] | None:
    for e in bibliography or []:
        try:
            if int(e.get("n")) == int(n):
                return {
                    "n": int(n),
                    "text": str(e.get("text") or ""),
                    "doi": str(e.get("doi") or "") or (extract_doi(str(e.get("text") or "")) or ""),
                }
        except (TypeError, ValueError):
            continue
    return None


def hints_for_sentence(
    text: str,
    bibliography: list[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    """매칭된 각주만 [{n, text, doi}]."""
    rows: list[dict[str, Any]] = []
    for n in parse_cite_numbers(text):
        hit = lookup_reference(n, bibliography)
        if hit and hit.get("text"):
            rows.append(hit)
    return rows


def bibliography_public(raw: list[Any] | None) -> list[dict[str, Any]]:
    """API/캐시용 정규화 — 이상한 값 방어."""
    out: list[dict[str, Any]] = []
    if not isinstance(raw, list):
        return out
    seen: set[int] = set()
    for item in raw:
        if not isinstance(item, dict):
            continue
        try:
            n = int(item.get("n"))
        except (TypeError, ValueError):
            continue
        if n in seen or not (1 <= n <= 9999):
            continue
        text = str(item.get("text") or "").strip()
        if len(text) < 3:
            continue
        seen.add(n)
        doi = str(item.get("doi") or "") or (extract_doi(text) or "")
        out.append({"n": n, "text": text[:2000], "doi": doi})
    out.sort(key=lambda e: e["n"])
    return out
