# -*- coding: utf-8 -*-
"""design/218 — soft pairing key (article/SI-prefix drift) + merge eligibility."""

from __future__ import annotations

from sentence_reading.api.supplementary_merge import merge_supplementary
from sentence_reading.cache import paper_cache as pc
from sentence_reading.cache.paper_cache import (
    normalize_pairing_key,
    normalize_title_key,
)
from sentence_reading.cache.supplementary_library import (
    apply_pairing_pass,
    can_merge_supplementary,
)
from sentence_reading.models import PaperSession, Sentence


def test_normalize_pairing_key_strips_articles() -> None:
    a = (
        "Optimizing the Ni/Cu Ratio in Ni-Cu Nanoparticle Catalysts "
        "for the Methane Dry Reforming"
    )
    b = (
        "Optimizing the Ni/Cu Ratio in Ni-Cu Nanoparticle Catalysts "
        "for Methane Dry Reforming"
    )
    assert normalize_title_key(a) != normalize_title_key(b)
    assert normalize_pairing_key(a) == normalize_pairing_key(b)
    assert " the " not in f" {normalize_pairing_key(a)} "


def test_normalize_pairing_key_strips_si_prefix() -> None:
    base = "Nickel copper alloy methane dry reforming study title long enough"
    with_si = f"Supporting Information: {base}"
    assert normalize_pairing_key(with_si) == normalize_pairing_key(base)


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


def test_soft_pair_ni_cu_the_drift_enables_merge(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(pc, "cache_root", lambda: tmp_path / "papers")
    main_title = (
        "Optimizing the Ni/Cu Ratio in Ni-Cu Nanoparticle Catalysts "
        "for the Methane Dry Reforming"
    )
    si_title = (
        "Optimizing the Ni/Cu Ratio in Ni-Cu Nanoparticle Catalysts "
        "for Methane Dry Reforming"
    )
    e_main = pc.save_paper_session(
        _session(main_title), debone=True, source="pdf", doc_role="main"
    )
    e_si = pc.save_paper_session(
        _session(si_title, section="supplementary"),
        debone=True,
        source="pdf",
        doc_role="supplementary",
    )
    assert e_main and e_si
    assert e_main["id"] != e_si["id"]

    rows = pc.list_cached_papers()
    by_id = {r["id"]: r for r in rows}
    assert by_id[e_main["id"]]["library_tag"] == "메인"
    assert by_id[e_si["id"]]["library_tag"] == "보충"
    assert by_id[e_main["id"]]["can_merge_supplementary"] is True
    assert by_id[e_main["id"]].get("paired_cache_id") == e_si["id"]
    assert by_id[e_si["id"]].get("paired_cache_id") == e_main["id"]


def test_soft_pair_merge_api_succeeds(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(pc, "cache_root", lambda: tmp_path / "papers")
    main_title = (
        "Optimizing the Ni/Cu Ratio in Ni-Cu Nanoparticle Catalysts "
        "for the Methane Dry Reforming"
    )
    si_title = (
        "Optimizing the Ni/Cu Ratio in Ni-Cu Nanoparticle Catalysts "
        "for Methane Dry Reforming"
    )
    e_main = pc.save_paper_session(
        _session(main_title), debone=True, source="pdf", doc_role="main"
    )
    e_si = pc.save_paper_session(
        _session(si_title, section="supplementary"),
        debone=True,
        source="pdf",
        doc_role="supplementary",
    )
    assert e_main and e_si

    result = merge_supplementary(str(e_main["id"]))
    assert result.get("ok") is True, result
    assert result.get("cache_id") == e_main["id"]
    assert int(result.get("sentence_count") or 0) == 2

    rows = pc.list_cached_papers()
    visible_ids = {r["id"] for r in rows}
    assert e_main["id"] in visible_ids
    assert e_si["id"] not in visible_ids
    # No orphan merged row under a different id for the same pairing.
    merged_rows = [r for r in rows if r.get("library_tag") == "메인+서플먼터리"]
    assert len(merged_rows) == 1
    assert merged_rows[0]["id"] == e_main["id"]
    assert int(merged_rows[0].get("sentence_count") or 0) == 2
    assert merged_rows[0].get("can_merge_supplementary") is False

    loaded, _ = pc.load_cached_session(str(e_main["id"]))
    assert loaded is not None
    assert len(loaded.sentences) == 2
    assert any(s.section == "supplementary" for s in loaded.sentences)


def test_exact_title_still_pairs(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(pc, "cache_root", lambda: tmp_path / "papers")
    title = "Photo catalytic water splitting study for pairing exact"
    e_main = pc.save_paper_session(
        _session(title), debone=True, source="pdf", doc_role="main"
    )
    e_si = pc.save_paper_session(
        _session(title, section="supplementary"),
        debone=True,
        source="pdf",
        doc_role="supplementary",
    )
    assert e_main and e_si
    entries = [dict(e) for e in pc._read_index().get("entries") or []]
    apply_pairing_pass(entries)
    main_e = next(e for e in entries if e["id"] == e_main["id"])
    assert can_merge_supplementary(main_e, entries) is True
