"""
design/251 Phase A — mate resolve (Unpaywall URL meta) + SI presence probe.
Bytes are fetched on-device; this module only returns candidates / status.
"""

from __future__ import annotations

import logging
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

log = logging.getLogger(__name__)

_DOI_RE = re.compile(r"^10\.\d{4,9}/[-._;()/:A-Za-z0-9]+$")
_UA = "A-sentence-reading/0.3.243 (mate-resolve; mailto:{mailto})"


def mate_direct_fetch_enabled() -> bool:
    raw = (os.environ.get("ASR_MATE_DIRECT_FETCH") or "1").strip().lower()
    return raw not in ("0", "false", "off", "no")


def _mailto() -> str:
    return (
        (os.environ.get("ASR_UNPAYWALL_EMAIL") or "").strip()
        or (os.environ.get("ASR_CROSSREF_MAILTO") or "").strip()
        or "asr-mate@localhost"
    )


def normalize_doi(raw: str) -> str | None:
    s = (raw or "").strip()
    if s.lower().startswith("https://doi.org/"):
        s = s[16:]
    elif s.lower().startswith("http://doi.org/"):
        s = s[15:]
    # ACS PDFs sometimes embed DOI+/suppl_file/stem_si_001.pdf
    low = s.lower()
    if "/suppl_file/" in low:
        s = s[: low.index("/suppl_file/")]
    s = s.strip().rstrip(".,;)")
    if not _DOI_RE.match(s):
        return None
    return s


def extract_acs_si_stem(raw: str) -> str | None:
    """From DOI text or head blob: …/suppl_file/{stem}_si_001.pdf → stem."""
    m = re.search(
        r"/suppl_file/([A-Za-z0-9._-]+)_si_00\d+\.pdf",
        raw or "",
        re.I,
    )
    if not m:
        return None
    return m.group(1)


# ACS SI short codes observed in lab corpus (design/251 Phase C seed).
_ACS_SI_PREFIX: dict[str, str] = {
    "acscatal": "cs",
    "acsami": "am",
    "acsanm": "an",
    "jacsat": "ja",
    "iecr": "ie",
    "jpcc": "jp",
    "accounts": "ar",
    "nanolett": "nl",
    "chemrev": "cr",
}


def _http_get_json(url: str, *, timeout: float = 12.0) -> dict[str, Any] | None:
    req = urllib.request.Request(
        url,
        headers={"User-Agent": _UA.format(mailto=_mailto()), "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as res:
            import json

            data = json.loads(res.read().decode("utf-8", errors="replace"))
            return data if isinstance(data, dict) else None
    except (urllib.error.URLError, TimeoutError, ValueError, OSError) as exc:
        log.info("mate http json fail: %s", type(exc).__name__)
        return None


def _http_head_or_get_ok(url: str, *, timeout: float = 10.0) -> tuple[bool, str]:
    """Return (ok_pdfish, content_type_prefix)."""
    for method in ("HEAD", "GET"):
        req = urllib.request.Request(
            url,
            method=method,
            headers={"User-Agent": _UA.format(mailto=_mailto())},
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as res:
                ctype = (res.headers.get("Content-Type") or "").lower()
                if method == "GET":
                    chunk = res.read(16)
                    if chunk.startswith(b"%PDF") or chunk.startswith(b"PK"):
                        return True, ctype.split(";")[0]
                    if b"<html" in chunk.lower() or b"<!doctype" in chunk.lower():
                        return False, "text/html"
                if "pdf" in ctype or "octet-stream" in ctype or "zip" in ctype:
                    return True, ctype.split(";")[0]
                if "html" in ctype:
                    return False, "text/html"
                # HEAD without useful type — try GET once
                if method == "HEAD":
                    continue
                return False, ctype.split(";")[0]
        except urllib.error.HTTPError as exc:
            if exc.code in (404, 410):
                return False, f"http_{exc.code}"
            if method == "HEAD":
                continue
            return False, f"http_{exc.code}"
        except (urllib.error.URLError, TimeoutError, OSError):
            if method == "HEAD":
                continue
            return False, "network"
    return False, "unknown"


def unpaywall_candidates(doi: str) -> list[dict[str, Any]]:
    email = urllib.parse.quote(_mailto())
    url = f"https://api.unpaywall.org/v2/{urllib.parse.quote(doi)}?email={email}"
    data = _http_get_json(url)
    if not data:
        return []
    out: list[dict[str, Any]] = []
    locs = []
    best = data.get("best_oa_location")
    if isinstance(best, dict):
        locs.append(best)
    more = data.get("oa_locations")
    if isinstance(more, list):
        for loc in more:
            if isinstance(loc, dict) and loc not in locs:
                locs.append(loc)
    for loc in locs:
        pdf = (loc.get("url_for_pdf") or "").strip()
        land = (loc.get("url_for_landing_page") or loc.get("url") or "").strip()
        host = ""
        target = pdf or land
        if target:
            try:
                host = urllib.parse.urlparse(target).hostname or ""
            except ValueError:
                host = ""
        if pdf:
            out.append(
                {
                    "tier": "oa",
                    "source": "unpaywall",
                    "url": pdf,
                    "kind": "pdf",
                    "license": (loc.get("license") or data.get("oa_status") or "")[:80],
                    "host": host,
                }
            )
        elif land:
            out.append(
                {
                    "tier": "oa",
                    "source": "unpaywall_landing",
                    "url": land,
                    "kind": "landing",
                    "license": (loc.get("license") or data.get("oa_status") or "")[:80],
                    "host": host,
                }
            )
    return out


def _acs_si_candidates(doi: str, *, si_stem: str | None = None) -> list[str]:
    # pubs.acs.org/doi/suppl/{doi}/suppl_file/{stem}_si_001.pdf
    last = doi.split("/")[-1]
    stems: set[str] = set()
    if si_stem:
        stems.add(si_stem.strip())
    # acscatal.2c02045 → cs2c02045 via journal map
    m = re.match(r"^(acs)?([a-z]+)\.([a-z0-9]+)$", last, re.I)
    if m:
        jkey = (("acs" + m.group(2)) if not m.group(1) else "acs" + m.group(2)).lower()
        jkey2 = m.group(2).lower()
        art = m.group(3)
        pref = _ACS_SI_PREFIX.get(jkey) or _ACS_SI_PREFIX.get(jkey2)
        if pref:
            stems.add(pref + art)
        stems.add(jkey2[:2] + art)
    # acs.iecr.3c00272
    m3 = re.match(r"^acs\.([a-z]+)\.([a-z0-9]+)$", last, re.I)
    if m3:
        j = m3.group(1).lower()
        art = m3.group(2)
        pref = _ACS_SI_PREFIX.get(j) or _ACS_SI_PREFIX.get("acs." + j)
        if pref:
            stems.add(pref + art)
    stems.add(last.replace(".", ""))
    if "." in last:
        stems.add(last.split(".")[-1])
    urls: list[str] = []
    base = f"https://pubs.acs.org/doi/suppl/{doi}/suppl_file/"
    for stem in stems:
        stem = re.sub(r"[^A-Za-z0-9._-]", "", stem)
        if not stem:
            continue
        urls.append(f"{base}{stem}_si_001.pdf")
        urls.append(f"{base}{stem.lower()}_si_001.pdf")
    seen: set[str] = set()
    out: list[str] = []
    for u in urls:
        if u not in seen:
            seen.add(u)
            out.append(u)
    return out[:12]


def _rsc_si_candidates(doi: str) -> list[str]:
    # 10.1039/d4se00467a → often .../suppdata/d4/se/d4se00467a/d4se00467a1.pdf
    last = doi.split("/")[-1].lower()
    urls = [
        f"https://www.rsc.org/suppdata/{last[:2]}/{last[2:4]}/{last}/{last}1.pdf",
        f"https://www.rsc.org/suppdata/{last[:2]}/{last[2:4]}/{last}/{last}_si.pdf",
        f"https://pubs.rsc.org/en/content/articlelanding/{doi}",
    ]
    if len(last) >= 4:
        urls.append(
            f"https://www.rsc.org/suppdata/{last[0:2]}/{last[2:4]}/{last}/{last}1.pdf"
        )
    return urls


def _nature_si_hint(doi: str) -> list[str]:
    # Nature supporting often behind article page; no stable anonymous URL — landing only
    last = doi.split("/")[-1]
    return [
        f"https://www.nature.com/articles/{last}",
        f"https://doi.org/{doi}",
    ]


def pattern_si_candidates(
    doi: str, *, si_stem: str | None = None
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    if doi.startswith("10.1021/"):
        for u in _acs_si_candidates(doi, si_stem=si_stem):
            host = urllib.parse.urlparse(u).hostname or ""
            out.append(
                {
                    "tier": "pattern",
                    "source": "acs_si_001",
                    "url": u,
                    "kind": "pdf",
                    "license": "",
                    "host": host,
                }
            )
    elif doi.startswith("10.1039/"):
        for u in _rsc_si_candidates(doi):
            host = urllib.parse.urlparse(u).hostname or ""
            kind = "pdf" if u.endswith(".pdf") else "landing"
            out.append(
                {
                    "tier": "pattern",
                    "source": "rsc_suppdata",
                    "url": u,
                    "kind": kind,
                    "license": "",
                    "host": host,
                }
            )
    elif doi.startswith("10.1038/"):
        for u in _nature_si_hint(doi):
            host = urllib.parse.urlparse(u).hostname or ""
            out.append(
                {
                    "tier": "pattern",
                    "source": "nature_landing",
                    "url": u,
                    "kind": "landing",
                    "license": "",
                    "host": host,
                }
            )
    return out


_ABSENT_MARKERS = (
    "no supporting information",
    "no supplementary information",
    "supporting information is not available",
    "supplementary information is not available",
    "does not have supplementary",
    "no associated supplementary",
    "there are no supplementary",
)
_PRESENT_MARKERS = (
    "supporting information",
    "supplementary information",
    "supplementary material",
    "electronic supplementary",
    "suppl_file",
    "moesm",
    "mmc1",
    "si_001",
)


def _fetch_text(url: str, *, timeout: float = 12.0, max_bytes: int = 400_000) -> str:
    req = urllib.request.Request(
        url,
        headers={"User-Agent": _UA.format(mailto=_mailto()), "Accept": "text/html,*/*"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as res:
            return res.read(max_bytes).decode("utf-8", errors="replace").lower()
    except (urllib.error.URLError, TimeoutError, OSError):
        return ""


def probe_si_status(doi: str, *, si_stem: str | None = None) -> dict[str, Any]:
    """
    Returns si_status: absent | available | unknown, plus pdf candidates when available.
    Uses allowlisted pattern HEAD checks + light landing HTML markers (no Cloudflare bypass).
    """
    d = normalize_doi(doi)
    if not d:
        return {"ok": False, "error": "bad_doi", "si_status": "unknown", "candidates": []}

    stem = (si_stem or "").strip() or extract_acs_si_stem(doi)
    candidates = pattern_si_candidates(d, si_stem=stem or None)
    pdf_hits: list[dict[str, Any]] = []
    for c in candidates:
        if c.get("kind") != "pdf":
            continue
        ok, ctype = _http_head_or_get_ok(str(c["url"]))
        if ok:
            c = dict(c)
            c["content_type"] = ctype
            pdf_hits.append(c)
            break  # one is enough for available

    if pdf_hits:
        return {
            "ok": True,
            "si_status": "available",
            "candidates": pdf_hits,
            "doi_ok": True,
        }

    # Landing HTML heuristics (doi.org redirect)
    html = _fetch_text(f"https://doi.org/{d}")
    if not html:
        return {"ok": True, "si_status": "unknown", "candidates": [], "doi_ok": True}

    if any(m in html for m in _ABSENT_MARKERS):
        return {"ok": True, "si_status": "absent", "candidates": [], "doi_ok": True}

    # ACS often lists "Supporting Information" with PDF link text
    if d.startswith("10.1021/") and "supporting information" in html:
        if "si_001" in html or "suppl_file" in html or ".pdf" in html:
            return {
                "ok": True,
                "si_status": "available",
                "candidates": candidates[:3],
                "doi_ok": True,
            }

    if any(m in html for m in _PRESENT_MARKERS) and (
        "download" in html or ".pdf" in html or "suppl" in html
    ):
        return {
            "ok": True,
            "si_status": "available",
            "candidates": [c for c in candidates if c.get("kind") == "landing"][:2],
            "doi_ok": True,
        }

    # Explicit empty SI section patterns (weak → unknown rather than false absent)
    if "supporting information" not in html and "supplementary" not in html:
        # Many paywalled pages omit SI section when none — still unknown if paywall shell
        if "captcha" in html or "cloudflare" in html or "challenge-platform" in html:
            return {"ok": True, "si_status": "unknown", "candidates": [], "doi_ok": True}
        # Soft absent only for ACS article pages that clearly lack SI wording
        if d.startswith("10.1021/") and "pubs.acs.org" in html:
            return {"ok": True, "si_status": "absent", "candidates": [], "doi_ok": True}

    return {"ok": True, "si_status": "unknown", "candidates": [], "doi_ok": True}


def resolve_mate(
    doi: str, want: str, *, si_stem: str | None = None
) -> dict[str, Any]:
    """want: main | si"""
    d = normalize_doi(doi)
    w = (want or "main").strip().lower()
    if w not in ("main", "si"):
        w = "main"
    if not d:
        return {
            "ok": False,
            "error": "bad_doi",
            "candidates": [],
            "fallback_browser": "",
            "si_status": "unknown",
        }
    fallback = f"https://doi.org/{d}"
    if not mate_direct_fetch_enabled():
        return {
            "ok": True,
            "enabled": False,
            "candidates": [],
            "fallback_browser": fallback,
            "si_status": "unknown",
        }

    if w == "si":
        probed = probe_si_status(d, si_stem=si_stem)
        return {
            "ok": True,
            "enabled": True,
            "want": "si",
            "candidates": probed.get("candidates") or [],
            "fallback_browser": fallback,
            "si_status": probed.get("si_status") or "unknown",
        }

    # main: Unpaywall first
    cands = unpaywall_candidates(d)
    return {
        "ok": True,
        "enabled": True,
        "want": "main",
        "candidates": cands,
        "fallback_browser": fallback,
        "si_status": "unknown",
    }
