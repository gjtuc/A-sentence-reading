# -*- coding: utf-8 -*-
"""design/492 — documents attached behind a paper, linked by file number."""

from __future__ import annotations

from sentence_reading.api.supplementary_merge import attach_parts, merge_supplementary
from sentence_reading.cache import doc_parts as dp
from sentence_reading.cache import paper_cache as pc
from sentence_reading.cache.supplementary_library import list_entries_for_api
from sentence_reading.llm import papers_gcs as pg
from sentence_reading.models import PaperSession, Sentence

_TITLE = "Platinum single atom catalyst attach parts fixture title for design 492"


def _session(title: str, n: int = 1, prefix: str = "s") -> PaperSession:
    return PaperSession(
        title=title,
        sentences=[
            Sentence(
                id=f"{prefix}-{i + 1}",
                text=f"Sentence {i + 1} of {title[:20]} that is long enough to keep.",
                section="introduction",
            )
            for i in range(n)
        ],
        figures=[],
    )


def _setup(tmp_path, monkeypatch):
    monkeypatch.setattr(pc, "cache_root", lambda: tmp_path / "papers")
    monkeypatch.setattr(pg, "gcs_papers_ready", lambda: False)
    main = pc.save_paper_session(
        _session(_TITLE, 2), source="pdf", doc_role="main",
        source_name="C:/dl/s41467-021-24079-8.pdf",
    )
    si = pc.save_paper_session(
        _session("Supporting Information " + _TITLE, 1),
        source="pdf", doc_role="supplementary",
        source_name="41467_2021_24079_MOESM1_ESM.pdf",
    )
    review = pc.save_paper_session(
        _session("REVIEWER COMMENTS", 3), source="pdf", doc_role="main",
        doc_kind="review", content_hash="c" * 64, source_name="41467_2021_24079_MOESM2_ESM.pdf",
    )
    return main, si, review


def test_file_article_key_links_nature_main_si_and_review() -> None:
    k = dp.file_article_key("s41467-021-24079-8.pdf")
    assert k == "n:41467-21-24079"
    assert dp.file_article_key("41467_2021_24079_MOESM1_ESM.pdf") == k
    assert dp.file_article_key("41467_2021_24079_MOESM2_ESM.pdf") == k
    assert dp.file_article_key("1-s2.0-S0360319921012345-main.pdf") == dp.file_article_key(
        "1-s2.0-S0360319921012345-mmc1.pdf"
    )
    assert dp.file_article_key("ja1c01234_si_001.pdf") == dp.file_article_key("ja1c01234.pdf")
    assert dp.file_article_key("paper.pdf") == ""
    assert dp.file_article_key("main.pdf") == ""


def test_source_name_kept_across_saves_and_listed(tmp_path, monkeypatch) -> None:
    main, _si, _review = _setup(tmp_path, monkeypatch)
    pc.save_paper_session(_session(_TITLE, 2), source="pdf", doc_role="main")
    rows = {r["id"]: r for r in list_entries_for_api(pc._read_index()["entries"])}
    assert rows[main["id"]]["source_name"] == "s41467-021-24079-8.pdf"


def test_attach_si_and_review_in_order(tmp_path, monkeypatch) -> None:
    main, si, review = _setup(tmp_path, monkeypatch)
    result = attach_parts(
        main["id"],
        [{"id": si["id"], "section": "supplementary"}, {"id": review["id"], "section": "review"}],
    )
    assert result.get("ok") is True, result
    assert result["sentence_count"] == 6
    assert result["library_tag"] == "메인+보충+심사"
    session, _ = pc.load_cached_session(main["id"])
    assert [s.section for s in session.sentences] == [
        "introduction", "introduction", "supplementary", "review", "review", "review",
    ]
    assert len({s.id for s in session.sentences}) == 6
    by_id = {e["id"]: e for e in pc._read_index()["entries"]}
    assert by_id[si["id"]]["hidden_in_library"] is True
    assert by_id[review["id"]]["hidden_in_library"] is True
    rows = {r["id"]: r for r in list_entries_for_api(list(by_id.values()))}
    assert set(rows) == {main["id"]}
    assert rows[main["id"]]["merged_sections"] == ["supplementary", "review"]
    assert rows[main["id"]]["library_tag"] == "메인+보충+심사"


def test_attach_again_skips_parts_already_inside(tmp_path, monkeypatch) -> None:
    main, si, review = _setup(tmp_path, monkeypatch)
    assert attach_parts(main["id"], [{"id": si["id"], "section": "supplementary"}])["ok"]
    again = attach_parts(main["id"], [{"id": si["id"], "section": "supplementary"}])
    assert again.get("already") is True
    more = attach_parts(main["id"], [{"id": review["id"], "section": "review"}])
    assert more.get("ok") is True and more["sentence_count"] == 6
    assert [p["id"] for p in more["merged_parts"]] == [si["id"], review["id"]]


def test_attach_refuses_merged_part_and_self(tmp_path, monkeypatch) -> None:
    main, si, review = _setup(tmp_path, monkeypatch)
    assert attach_parts(main["id"], [{"id": main["id"]}]).get("error") == "bad_parts"
    attach_parts(main["id"], [{"id": si["id"], "section": "supplementary"}])
    bad = attach_parts(review["id"], [{"id": main["id"], "section": "attached"}])
    assert bad.get("error") == "merge_not_allowed"


def test_old_pair_merge_still_tags_main_plus_si(tmp_path, monkeypatch) -> None:
    main, si, _review = _setup(tmp_path, monkeypatch)
    result = merge_supplementary(main["id"])
    assert result.get("ok") is True, result
    assert result["library_tag"] == "메인+서플먼터리"
    assert result["merged_supplementary_id"] == si["id"]
