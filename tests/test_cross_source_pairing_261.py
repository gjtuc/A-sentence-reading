# -*- coding: utf-8 -*-
"""design/261 — cross-source pairing (pdf+docx) + strict 1+1."""

from __future__ import annotations

from sentence_reading.cache import paper_cache as pc
from sentence_reading.cache.supplementary_library import (
    apply_pairing_pass,
    can_merge_supplementary,
)
from sentence_reading.models import PaperSession, Sentence


def _session(title: str, *, section: str = "introduction") -> PaperSession:
    return PaperSession(
        title=title + " " + ("x" * 24),
        sentences=[
            Sentence(
                id="s-1",
                text="Introduction sentence with enough length here.",
                section=section,
            )
        ],
        figures=[],
    )


def test_cross_source_pdf_docx_pairs(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(pc, "cache_root", lambda: tmp_path / "papers")
    title = "Connection between alumina doping methodology and performance review"
    e_main = pc.save_paper_session(
        _session(title), debone=True, source="pdf", doc_role="main"
    )
    e_si = pc.save_paper_session(
        _session(title, section="supplementary"),
        debone=True,
        source="docx",
        doc_role="supplementary",
    )
    assert e_main and e_si
    rows = pc.list_cached_papers()
    by_id = {r["id"]: r for r in rows}
    assert by_id[e_main["id"]].get("paired_cache_id") == e_si["id"]
    assert by_id[e_si["id"]].get("paired_cache_id") == e_main["id"]
    assert by_id[e_main["id"]]["can_merge_supplementary"] is True


def test_cross_source_two_mains_unpaired(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(pc, "cache_root", lambda: tmp_path / "papers")
    title = "Ambiguous catalyst review title for pairing gap case xx"
    e1 = pc.save_paper_session(
        _session(title), debone=True, source="pdf", doc_role="main"
    )
    e2 = pc.save_paper_session(
        _session(title), debone=True, source="docx", doc_role="main"
    )
    assert e1 and e2 and e1["id"] != e2["id"]
    entries = [dict(e) for e in pc._read_index().get("entries") or []]
    apply_pairing_pass(entries)
    paired = [e for e in entries if e.get("paired_cache_id")]
    assert paired == []


def test_dedup_keeps_pdf_and_docx_slots(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(pc, "cache_root", lambda: tmp_path / "papers")
    title = "Dedup four slots same title different source role xx"
    a = pc.save_paper_session(
        _session(title), debone=True, source="pdf", doc_role="main"
    )
    b = pc.save_paper_session(
        _session(title, section="supplementary"),
        debone=True,
        source="docx",
        doc_role="supplementary",
    )
    assert a and b
    assert a["id"] != b["id"]
    entries = [dict(e) for e in pc._read_index().get("entries") or []]
    apply_pairing_pass(entries)
    main_e = next(e for e in entries if e["id"] == a["id"])
    assert can_merge_supplementary(main_e, entries) is True
