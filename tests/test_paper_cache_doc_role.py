# -*- coding: utf-8 -*-
"""design/152 — cache dedup by title_key + source + doc_role."""

from __future__ import annotations

from sentence_reading.cache import paper_cache as pc
from sentence_reading.models import PaperSession, Sentence


def _session(title: str) -> PaperSession:
    long_title = title + " " + ("x" * 30)
    return PaperSession(
        title=long_title,
        sentences=[
            Sentence(
                id="s-1",
                text="Introduction sentence with enough length here.",
                section="introduction",
            )
        ],
        figures=[],
    )


def test_same_title_two_pdf_roles_two_ids(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(pc, "cache_root", lambda: tmp_path / "papers")
    title = "Photo catalytic water splitting study"
    main = _session(title)
    si = _session(title)

    e1 = pc.save_paper_session(main, debone=True, source="pdf", doc_role="main")
    e2 = pc.save_paper_session(si, debone=True, source="pdf", doc_role="supplementary")
    assert e1 is not None and e2 is not None
    assert e1["id"] != e2["id"]

    rows = pc.list_cached_papers()
    ids = {r["id"] for r in rows if r["title"].startswith(title.split()[0])}
    assert e1["id"] in ids
    assert e2["id"] in ids
    tags = {r["id"]: r["library_tag"] for r in rows}
    assert tags[e1["id"]] == "메인"
    assert tags[e2["id"]] == "보충"


def test_reupload_si_updates_si_only(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(pc, "cache_root", lambda: tmp_path / "papers")
    title = "Electrochemical nitrogen fixation paper"
    main = _session(title)
    si_v1 = _session(title)
    si_v2 = _session(title)
    si_v2.sentences.append(
        Sentence(
            id="s-2",
            text="Another supplementary sentence with sufficient length.",
            section="supplementary",
        )
    )

    e_main = pc.save_paper_session(main, debone=True, source="pdf", doc_role="main")
    e_si1 = pc.save_paper_session(si_v1, debone=True, source="pdf", doc_role="supplementary")
    assert e_main and e_si1
    e_si2 = pc.save_paper_session(si_v2, debone=True, source="pdf", doc_role="supplementary")
    assert e_si2 is not None
    assert e_si2["id"] == e_si1["id"]
    assert e_si2["sentence_count"] == 2

    loaded_main, _ = pc.load_cached_session(e_main["id"])  # type: ignore[index]
    assert loaded_main is not None
    assert len(loaded_main.sentences) == 1
