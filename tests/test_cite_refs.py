"""문헌 각주 → References → DOI/Crossref (0.3.3 · design/41)."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from sentence_reading.api.app import app
from sentence_reading.cache import paper_cache as pc
from sentence_reading.cite_refs import (
    bibliography_public,
    extract_bibliography,
    extract_doi,
    hints_for_sentence,
    parse_cite_numbers,
)
from sentence_reading.llm import crossref_resolve as cr
from sentence_reading.models import PaperSession, Sentence, build_mock_session

ROOT = Path(__file__).resolve().parents[1]

SAMPLE_PAPER = """
Title: Example

The catalyst was stable.[1] Rates rose with loading.[2-3]

References
1. B. Liu, J. Sunarso, Y. Zhang, G. Yang, W. Zhou, Z. Shao, ChemElectroChem
2018, 5, 785.
2. A. Smith, J. Catal. 2019, 370, 1-10. doi:10.1016/j.jcat.2019.01.001
3. C. Lee et al., Nature 2020, 580, 123.
"""


def test_status_cite_flag() -> None:
    st = TestClient(app).get("/api/status").json()
    assert st["version"] == "0.3.130"
    assert st["cite_ref_open"] is True


def test_design_41_contract() -> None:
    design = (ROOT / "docs" / "design" / "41-cite-ref-open.md").read_text(
        encoding="utf-8"
    )
    assert "0.2.49" in design
    assert "Crossref" in design or "crossref" in design
    assert "DOI" in design
    assert "Live Enable" in design or "IPS" in design
    assert "Flutter" in design


def test_ui_assets() -> None:
    html = (ROOT / "src" / "sentence_reading" / "static" / "index.html").read_text(
        encoding="utf-8"
    )
    assert 'id="citeRefHints"' in html
    assert 'id="citeRefPanel"' in html
    assert "cite_refs.js" in html
    js = (ROOT / "src" / "sentence_reading" / "static" / "app.js").read_text(
        encoding="utf-8"
    )
    assert "renderCiteRefHints" in js
    assert "/api/cite/resolve" in js
    assert "design/41" in js or "citeRefOpenBtn" in js
    served = TestClient(app).get("/").text
    assert "cite_refs.js?v=0.3.130" in served
    assert "app.js?v=0.3.130" in served


def test_parse_and_extract() -> None:
    assert parse_cite_numbers("Hello.[1] More.[2-3,5]") == [1, 2, 3, 5]
    assert parse_cite_numbers("x<sup>12</sup> y") == [12]
    assert parse_cite_numbers("") == []
    assert parse_cite_numbers("[99999]") == []  # over cap via expand? 99999 > 9999
    # single huge number rejected
    assert parse_cite_numbers("[0]") == []
    bib = extract_bibliography(SAMPLE_PAPER)
    assert [e["n"] for e in bib] == [1, 2, 3]
    assert "ChemElectroChem" in bib[0]["text"]
    assert bib[1]["doi"].startswith("10.1016/")
    hints = hints_for_sentence("stable.[1]", bib)
    assert hints[0]["n"] == 1
    assert hints_for_sentence("no cites", bib) == []
    assert hints_for_sentence("[9]", bib) == []


def test_plain_trailing_hints_for_sentence() -> None:
    minus = "\u2212"
    bib = [
        {"n": 6, "text": "Ref six long enough.", "doi": ""},
        {"n": 7, "text": "Ref seven long enough.", "doi": ""},
    ]
    hints = hints_for_sentence(f"MDR reaction.6{minus}9", bib)
    assert [h["n"] for h in hints] == [6, 7]


def test_extract_edge_garbage() -> None:
    assert extract_bibliography("") == []
    assert extract_bibliography("no refs section") == []
    assert extract_bibliography("References\n\nnot numbered") == []


def test_extract_acs_bullet_references_header() -> None:
    text = (
        "Body text here.\n\n"
        "■REFERENCES\n"
        "(1) Bian, Z.; Das, S. A Review on Bimetallic Nickel-Based Catalysts.\n"
        "(2) Smith, J.; Doe, A. Another reference entry long enough.\n"
    )
    bib = extract_bibliography(text)
    assert [e["n"] for e in bib] == [1, 2]
    assert extract_doi("") is None
    assert extract_doi("doi:10.1000/xyz") == "10.1000/xyz"
    assert bibliography_public([{"n": "x", "text": "a"}, None, "z"]) == []
    assert bibliography_public([{"n": 1, "text": "ab"}]) == []  # too short
    assert bibliography_public([{"n": 1, "text": "long enough text"}])[0]["n"] == 1


def test_extract_acs_inline_references_same_line() -> None:
    """acsanm PDF: ■REFERENCES (7) Wang… (8) Han… on one line."""
    text = (
        "Ack text (62). ■REFERENCES (7) Wang, F.; Xu, L.; Zhang, J.; "
        "Tuning the metal-support interaction in catalysts for highly efficient "
        "methane dry reforming reaction. Appl. Catal., B 2016, 180 (0), 511−520. "
        "(8) Han, B.; Wang, F.; Zhang, L.; Syngas production from methane steam "
        "reforming and dry reforming reactions over sintering-resistant Ni@SiO2 "
        "catalyst. Res. Chem. Intermed. 2020, 46 (3), 1735−1748."
    )
    bib = extract_bibliography(text)
    assert [e["n"] for e in bib] == [7, 8]
    assert "Wang, F." in bib[0]["text"]


def test_mock_session_has_refs() -> None:
    data = build_mock_session().to_public_dict()
    assert data["references"]
    assert data["sentences"][0]["text"].endswith("[1]")


def test_cache_roundtrip_refs(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(pc, "cache_root", lambda: tmp_path)
    session = PaperSession(
        title="Cite Cache Paper Title Long Enough Here",
        sentences=[Sentence(id="s1", text="Claim.[1]", section="body")],
        references=[
            {"n": 1, "text": "B. Liu, ChemElectroChem 2018, 5, 785.", "doi": ""}
        ],
    )
    entry = pc.save_paper_session(session, debone=True, source="pdf")
    loaded, _ = pc.load_cached_session(entry["id"])
    assert loaded.references[0]["n"] == 1
    assert "ChemElectroChem" in loaded.references[0]["text"]


def test_resolve_doi_in_text() -> None:
    out = cr.resolve_citation("Something doi:10.1021/jacs.0c00000 end")
    assert out["ok"] is True
    assert out["source"] == "doi_in_text"
    assert "doi.org/10.1021/jacs.0c00000" in out["url"]


def test_resolve_empty_and_crossref_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    assert cr.resolve_citation("")["error"] == "empty"
    assert cr.resolve_citation("   ")["error"] == "empty"

    def boom(q: str) -> dict:
        return {"ok": False, "error": "crossref_network"}

    monkeypatch.setattr(cr, "_crossref_search", boom)
    out = cr.resolve_citation("B. Liu, ChemElectroChem 2018, 5, 785.")
    assert out["ok"] is True
    assert out["source"] == "scholar_fallback"
    assert "scholar.google.com" in out["url"]


def test_resolve_crossref_mock(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        cr,
        "_crossref_search",
        lambda q: {
            "ok": True,
            "url": "https://doi.org/10.1002/celc.201700999",
            "doi": "10.1002/celc.201700999",
            "source": "crossref",
            "title": "Mock",
        },
    )
    out = cr.resolve_citation("B. Liu ChemElectroChem 2018")
    assert out["source"] == "crossref"
    assert out["doi"].startswith("10.1002/")


def test_api_cite_resolve() -> None:
    client = TestClient(app)
    r = client.post("/api/cite/resolve", json={"text": "doi:10.1000/test.doi"})
    assert r.status_code == 200
    data = r.json()
    assert data["ok"] is True
    assert data["source"] == "doi_in_text"
    bad = client.post("/api/cite/resolve", json={"text": 123})
    assert bad.json()["ok"] is False
    empty = client.post("/api/cite/resolve", json={"text": ""})
    assert empty.json()["ok"] is False


def test_ingest_mentions_bibliography() -> None:
    src = (ROOT / "src" / "sentence_reading" / "api" / "app.py").read_text(
        encoding="utf-8"
    )
    assert "extract_bibliography" in src
    assert 'stage="translate"' in src or "references=" in src
    assert "/api/cite/resolve" in src
