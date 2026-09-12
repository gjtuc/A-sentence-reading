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
    "acsenergylett": "nz",
    "acsomega": "ao",
    "inorgchem": "ic",
    "organomet": "om",
    "langmuir": "la",
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
    """RSC ESI path forms (corpus + known RSC publishing paths).

    Example: c5cs00520e → /suppdata/c5/cs/c5cs00520e/c5cs00520e1.pdf
    """
    last = doi.split("/")[-1].lower()
    urls: list[str] = []
    if len(last) >= 4:
        a, b = last[:2], last[2:4]
        for host in ("https://www.rsc.org", "http://www.rsc.org"):
            urls.append(f"{host}/suppdata/{a}/{b}/{last}/{last}1.pdf")
            urls.append(f"{host}/suppdata/{a}/{b}/{last}/{last}1_suppl.pdf")
            urls.append(f"{host}/suppdata/{b}/{a}/{last}/{last}1.pdf")
        # journal / c{year digit} / id  (cs/c4/d4cs... from d4cs...)
        if last[0].isalpha() and last[1].isdigit():
            j = last[2:4]
            cy = "c" + last[1]
            for host in ("https://www.rsc.org", "http://www.rsc.org"):
                urls.append(f"{host}/suppdata/{j}/{cy}/{last}/{last}1.pdf")
    urls.append(f"https://pubs.rsc.org/en/content/articlelanding/{doi}")
    if last.startswith("d4") and len(last) >= 4:
        urls.append(
            f"https://pubs.rsc.org/en/content/articlelanding/2024/{last[2:4]}/{last}"
        )
    if last.startswith("d3") and len(last) >= 4:
        urls.append(
            f"https://pubs.rsc.org/en/content/articlelanding/2023/{last[2:4]}/{last}"
        )
    seen: set[str] = set()
    out: list[str] = []
    for u in urls:
        if u not in seen:
            seen.add(u)
            out.append(u)
    return out[:16]


def _nature_si_hint(doi: str) -> list[str]:
    """Nature/Springer ESM PDF + landing.

    Corpus: 41929_2026_1513_MOESM1_ESM.pdf ↔ 10.1038/s41929-026-01513-y
    """
    last = doi.split("/")[-1]
    urls: list[str] = []
    m = re.match(r"^s?(\d+)-(\d+)-(\d+)(?:-[a-z]+)?$", last, re.I)
    if m:
        years = [m.group(2)]
        y = m.group(2)
        if len(y) == 3 and y.startswith("0"):
            years.append("2" + y)  # 026 → 2026 (corpus MOESM naming)
        elif len(y) == 2:
            years.append("20" + y)
        enc = urllib.parse.quote(f"art:{doi}", safe="")
        arts = [m.group(3)]
        if m.group(3).startswith("0") and m.group(3).lstrip("0"):
            arts.append(m.group(3).lstrip("0"))  # 01513 → 1513 (corpus MOESM)
        for year in years:
            for art in arts:
                stem = f"{m.group(1)}_{year}_{art}_MOESM1_ESM.pdf"
                urls.append(
                    f"https://static-content.springer.com/esm/{enc}/MediaObjects/{stem}"
                )
    urls.extend(
        [
            f"https://www.nature.com/articles/{last}",
            f"https://doi.org/{doi}",
        ]
    )
    return urls


def _wiley_si_candidates(doi: str) -> list[str]:
    return [
        f"https://onlinelibrary.wiley.com/doi/suppl/{doi}",
        (
            "https://onlinelibrary.wiley.com/action/downloadSupplement?doi="
            + urllib.parse.quote(doi)
            + "&file=supinfo"
        ),
        f"https://doi.org/{doi}",
    ]


def _iop_si_candidates(doi: str) -> list[str]:
    return [
        f"https://iopscience.iop.org/article/{doi}",
        f"https://doi.org/{doi}",
    ]


def pattern_si_candidates(
    doi: str, *, si_stem: str | None = None
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []

    def add(source: str, urls: list[str]) -> None:
        for u in urls:
            host = urllib.parse.urlparse(u).hostname or ""
            kind = "pdf" if u.lower().endswith((".pdf", ".zip")) else "landing"
            out.append(
                {
                    "tier": "pattern",
                    "source": source,
                    "url": u,
                    "kind": kind,
                    "license": "",
                    "host": host,
                }
            )

    if doi.startswith("10.1021/"):
        add("acs_si_001", _acs_si_candidates(doi, si_stem=si_stem))
    elif doi.startswith("10.1039/"):
        add("rsc_suppdata", _rsc_si_candidates(doi))
    elif doi.startswith("10.1038/"):
        add("nature_esm", _nature_si_hint(doi))
    elif doi.startswith("10.1002/"):
        add("wiley_suppl", _wiley_si_candidates(doi))
    elif doi.startswith("10.1088/"):
        add("iop_landing", _iop_si_candidates(doi))
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
    Returns si_status + candidates for *device* fetch.

    Server HEAD often hits Cloudflare 403 from Cloud Run/PC — that must NOT
    empty candidates. Always return PDF pattern URLs for the phone to try;
    only mark absent when HTML markers say so.
    """
    d = normalize_doi(doi)
    if not d:
        return {"ok": False, "error": "bad_doi", "si_status": "unknown", "candidates": []}

    stem = (si_stem or "").strip() or extract_acs_si_stem(doi)
    candidates = pattern_si_candidates(d, si_stem=stem or None)
    pdf_cands = [c for c in candidates if c.get("kind") == "pdf"]
    device_cands = pdf_cands[:8] or [
        c for c in candidates if c.get("kind") == "landing"
    ][:2]

    pdf_hits: list[dict[str, Any]] = []
    saw_cf = False
    saw_404 = 0
    for c in pdf_cands[:6]:
        ok, ctype = _http_head_or_get_ok(str(c["url"]))
        if ok:
            c2 = dict(c)
            c2["content_type"] = ctype
            pdf_hits.append(c2)
            break
        if ctype in ("http_403",) or "html" in (ctype or ""):
            saw_cf = True
        if ctype in ("http_404", "http_410"):
            saw_404 += 1

    if pdf_hits:
        return {
            "ok": True,
            "si_status": "available",
            "candidates": pdf_hits,
            "doi_ok": True,
            "server_verified": True,
        }

    html = _fetch_text(f"https://doi.org/{d}")
    if html and any(m in html for m in _ABSENT_MARKERS):
        return {
            "ok": True,
            "si_status": "absent",
            "candidates": [],
            "doi_ok": True,
        }

    if html:
        if any(
            m in html
            for m in ("captcha", "cloudflare", "challenge-platform", "just a moment")
        ):
            saw_cf = True
        if d.startswith("10.1021/") and "supporting information" in html:
            if "si_001" in html or "suppl_file" in html or ".pdf" in html:
                return {
                    "ok": True,
                    "si_status": "available",
                    "candidates": device_cands,
                    "doi_ok": True,
                }
        if (
            "supporting information" not in html
            and "supplementary" not in html
            and not saw_cf
            and d.startswith("10.1021/")
            and "pubs.acs.org" in html
        ):
            return {
                "ok": True,
                "si_status": "absent",
                "candidates": [],
                "doi_ok": True,
            }

    # Elsevier: no safe anonymous SI PDF template (mmc often docx) → browser.
    if d.startswith("10.1016/") and not pdf_cands:
        return {
            "ok": True,
            "si_status": "unknown",
            "candidates": [],
            "doi_ok": True,
        }

    _ = saw_404  # retained for future absent heuristics
    return {
        "ok": True,
        "si_status": "unknown",
        "candidates": device_cands,
        "doi_ok": True,
        "server_verified": False,
        "server_cf_blocked": saw_cf,
    }


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
