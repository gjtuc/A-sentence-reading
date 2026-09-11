# -*- coding: utf-8 -*-
"""design/232 remove recent strip · 233 advisory title chrome skip."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MOBILE = ROOT / "mobile"
FX = ROOT / "tests" / "fixtures" / "doc_role"
D232 = ROOT / "docs" / "design" / "232-pdf-import-remove-recent-strip.md"
D233 = ROOT / "docs" / "design" / "233-pdf-advisory-title-chrome-skip.md"


def test_designs_locked() -> None:
    a = D232.read_text(encoding="utf-8")
    b = D233.read_text(encoding="utf-8")
    assert "0.3.230" in a and "locked" in a.lower()
    assert "_RecentStrip" in a or "RecentStrip" in a or "최근" in a
    assert "0.3.230" in b and "locked" in b.lower()
    assert "Cite this" in b or "chrome" in b.lower()


def test_screen_has_no_recent_strip() -> None:
    screen = (
        MOBILE / "lib" / "screens" / "pdf_import_screen.dart"
    ).read_text(encoding="utf-8")
    assert "_RecentStrip" not in screen
    assert "pickerRecent" not in screen


def test_cache_schema_v3() -> None:
    cache = (
        MOBILE / "lib" / "api" / "pdf_advisory_cache_store.dart"
    ).read_text(encoding="utf-8")
    assert "kPdfAdvisoryCacheSchema = 3" in cache


def test_dart_chrome_helpers_present() -> None:
    title = (MOBILE / "lib" / "pdf" / "advisory_title.dart").read_text(
        encoding="utf-8"
    )
    assert "isAdvisoryTitleChrome" in title
    assert "Cite this" in title or "cite this" in title.lower()
    assert "PAPER" in title or "paper" in title
    assert "REVIEW" in title or "review" in title


def _port_guess(info: str, head: str, name: str) -> tuple[str, str]:
    """Minimal Python mirror of dart chrome skip + looksLikeTitle."""
    import re

    si = re.compile(
        r"^\s*(supplementary\s+(?:information|materials?|data)|supporting\s+information|electronic\s+supplementary)\b",
        re.I,
    )
    exact = re.compile(
        r"^(paper|review|article|research|research article|open access|"
        r"supporting information for|contents lists available|"
        r"available online)\b\.?$",
        re.I,
    )
    prefix = re.compile(
        r"^(cite this|cite this:|to cite this|doi:|https?://|www\.|"
        r"received |accepted |published |view the article|"
        r"this content was downloaded|citation:)",
        re.I,
    )
    journal = re.compile(
        r"(?i)(^journal of\b|^nature catalysis\b|^catal\.?\s*sci\.?\s*technol|"
        r"catalysis\s+science\s*(?:&|and)?\s*technology|"
        r"accounts of chemical research|green chemical engineering|"
        r"scientific reports|sustainable energy\s*(?:&|and)?\s*fuels|"
        r"applied physics|chem\.?\s*eng\.?\s*j)"
    )
    frag = re.compile(r"^(catalysis|technology|science\s*&?)$", re.I)

    def chrome(raw: str) -> bool:
        t = re.sub(r"\s+", " ", raw.strip())
        if not t:
            return True
        if exact.match(t) or prefix.match(t) or journal.search(t) or frag.match(t):
            return True
        if re.match(r"^[\d,\s\-–—]+$", t):
            return True
        return False

    def looks(raw: str) -> bool:
        t = re.sub(r"\s+", " ", raw.strip())
        if len(t) < 12 or len(t) > 200:
            return False
        if si.match(t) or chrome(t):
            return False
        if re.match(r"^[\d\W_]+$", t):
            return False
        digits = len(re.sub(r"\D", "", t))
        if digits > len(t) * 0.5:
            return False
        return True

    info = (info or "").strip()
    if looks(info):
        return "info", re.sub(r"\s+", " ", info)
    for line in head.splitlines():
        t = re.sub(r"\s+", " ", line.strip())
        if not t or si.match(t) or chrome(t) or len(t) < 12:
            continue
        if looks(t):
            return "head_line", t
    stem = name[:-4] if name.lower().endswith(".pdf") else name
    return "stem", stem


def test_iop_and_rsc_fixtures_skip_journal_chrome() -> None:
    iop = (FX / "title_iop_journal_chrome.txt").read_text(encoding="utf-8")
    src, title = _port_guess("", iop, "1361-6463.pdf")
    assert src == "head_line"
    assert "Journal of Physics" not in title
    assert "In situ and operando" in title

    rsc = (FX / "title_rsc_cite_chrome.txt").read_text(encoding="utf-8")
    src2, title2 = _port_guess("", rsc, "d3cy01612a.pdf")
    assert src2 == "head_line"
    assert "Cite this" not in title2
    assert "Catal. Sci" not in title2
    assert "Recent advances" in title2
