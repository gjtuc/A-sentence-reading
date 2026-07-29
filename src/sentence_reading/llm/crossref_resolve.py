"""
무엇을: 문헌 문자열 → 원문 URL (DOI 우선 · Crossref · Scholar 폴백) (design/41).
왜: 출판사별 검색창보다 DOI/Crossref가 안정적.
NOTE: Live Enable / IPS 는 Trading Gate — ASR 밖.
"""

from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from sentence_reading.cite_refs import extract_doi

log = logging.getLogger(__name__)

_CROSSREF = "https://api.crossref.org/works"
_TIMEOUT_S = 12.0
_MAX_QUERY = 500


def _mailto() -> str:
    # WHY: Crossref polite pool — 없으면 localhost 표기
    return (os.environ.get("ASR_CROSSREF_MAILTO") or "asr-reader@localhost").strip()


def doi_url(doi: str) -> str:
    d = (doi or "").strip().lstrip("/")
    if d.lower().startswith("https://doi.org/"):
        return d
    if d.lower().startswith("http://doi.org/"):
        return "https://" + d[7:]
    if d.lower().startswith("doi:"):
        d = d[4:].strip()
    return f"https://doi.org/{d}"


def scholar_url(query: str) -> str:
    q = (query or "").strip()[:_MAX_QUERY]
    return "https://scholar.google.com/scholar?" + urllib.parse.urlencode({"q": q})


def resolve_citation(text: str) -> dict[str, Any]:
    """
    { ok, url, doi?, source, title?, error? }
    빈/쓰레기 입력도 예외 없이 dict 반환.
    """
    plain = re_sub_ws(text)
    if not plain:
        return {"ok": False, "error": "empty", "url": "", "source": ""}
    if len(plain) > _MAX_QUERY * 4:
        plain = plain[: _MAX_QUERY * 4]

    doi = extract_doi(plain)
    if doi:
        return {
            "ok": True,
            "url": doi_url(doi),
            "doi": doi,
            "source": "doi_in_text",
            "title": "",
        }

    cr = _crossref_search(plain)
    if cr.get("ok"):
        return cr

    # WHY: Crossref 실패해도 사용자가 직접 찾을 수 있게 Scholar
    return {
        "ok": True,
        "url": scholar_url(plain),
        "doi": "",
        "source": "scholar_fallback",
        "title": "",
        "warning": cr.get("error") or "crossref_miss",
    }


def re_sub_ws(text: str) -> str:
    import re

    t = re.sub(r"<[^>]+>", " ", text or "")
    return re.sub(r"\s+", " ", t).strip()


def _crossref_search(query: str) -> dict[str, Any]:
    q = query[:_MAX_QUERY]
    params = urllib.parse.urlencode(
        {
            "query.bibliographic": q,
            "rows": "2",
            "mailto": _mailto(),
        }
    )
    url = f"{_CROSSREF}?{params}"
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": f"A-sentence-reading/0.2.49 (mailto:{_mailto()})",
            "Accept": "application/json",
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT_S) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        log.warning("crossref HTTP %s", exc.code)
        return {"ok": False, "error": f"crossref_http_{exc.code}"}
    except Exception as exc:  # noqa: BLE001
        log.warning("crossref failed: %s", exc)
        return {"ok": False, "error": "crossref_network"}

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return {"ok": False, "error": "crossref_bad_json"}

    items = (
        ((data.get("message") or {}).get("items"))
        if isinstance(data, dict)
        else None
    )
    if not isinstance(items, list) or not items:
        return {"ok": False, "error": "crossref_empty"}

    top = items[0] if isinstance(items[0], dict) else {}
    doi = str(top.get("DOI") or "").strip()
    title_l = top.get("title")
    title = ""
    if isinstance(title_l, list) and title_l:
        title = str(title_l[0] or "")
    elif isinstance(title_l, str):
        title = title_l

    if not doi:
        return {"ok": False, "error": "crossref_no_doi", "title": title}

    return {
        "ok": True,
        "url": doi_url(doi),
        "doi": doi,
        "source": "crossref",
        "title": title,
    }
