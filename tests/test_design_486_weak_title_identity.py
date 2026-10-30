# -*- coding: utf-8 -*-
"""design/486 - a short title is saved, and the file bytes say which paper it is."""

from __future__ import annotations

from sentence_reading.cache import paper_cache as pc
from sentence_reading.cache.supplementary_library import apply_pairing_pass
from sentence_reading.llm import papers_gcs as pg
from sentence_reading.models import PaperSession, Sentence

H1 = "a" * 64
H2 = "b" * 64


def _session(title: str, text: str = "Reviewer one asked for more controls here.") -> PaperSession:
    return PaperSession(
        title=title,
        sentences=[Sentence(id="s-1", text=text, section="body")],
        figures=[],
    )


def _ids() -> list[str]:
    return [e["id"] for e in pc._read_index().get("entries", [])]


def test_short_title_is_saved_with_a_content_hash(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(pc, "cache_root", lambda: tmp_path / "papers")
    e = pc.save_paper_session(_session("REVIEWER COMMENTS"), debone=True, content_hash=H1)
    assert e and e["title"] == "REVIEWER COMMENTS"
    assert _ids() == [e["id"]]


def test_short_title_without_a_hash_is_still_refused(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(pc, "cache_root", lambda: tmp_path / "papers")
    assert pc.save_paper_session(_session("REVIEWER COMMENTS"), debone=True) is None


def test_two_files_with_one_short_title_stay_apart(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(pc, "cache_root", lambda: tmp_path / "papers")
    a = pc.save_paper_session(_session("REVIEWER COMMENTS"), debone=True, content_hash=H1)
    b = pc.save_paper_session(_session("REVIEWER COMMENTS"), debone=True, content_hash=H2)
    assert a and b and a["id"] != b["id"]
    assert sorted(_ids()) == sorted([a["id"], b["id"]])


def test_the_same_file_again_reuses_its_row(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(pc, "cache_root", lambda: tmp_path / "papers")
    a = pc.save_paper_session(_session("REVIEWER COMMENTS"), debone=True, content_hash=H1)
    b = pc.save_paper_session(
        _session("REVIEWER COMMENTS", "A second pass of the same file."),
        debone=True,
        content_hash=H1,
    )
    assert a and b and a["id"] == b["id"]
    assert _ids() == [a["id"]]


def test_a_long_title_still_matches_by_title(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(pc, "cache_root", lambda: tmp_path / "papers")
    title = "Nickel copper alloy methane dry reforming study title"
    a = pc.save_paper_session(_session(title), debone=True, content_hash=H1)
    b = pc.save_paper_session(_session(title), debone=True, content_hash=H2)
    assert a and b and a["id"] == b["id"]


def test_the_gcs_index_merge_keeps_both_short_title_rows() -> None:
    row = {"title": "Peer review", "title_key": "peer review", "source": "pdf"}
    a = [{**row, "id": "aaaaaaaaaaaa", "content_hash": H1, "updated_at": "2026"}]
    b = [{**row, "id": "bbbbbbbbbbbb", "content_hash": H2, "updated_at": "2025"}]
    assert len(pg.merge_index_entries(a, b)) == 2
    c = [{**row, "id": "cccccccccccc", "content_hash": H1, "updated_at": "2027"}]
    assert [e["id"] for e in pg.merge_index_entries(a, c)] == ["cccccccccccc"]


def test_short_titles_do_not_pair() -> None:
    main = {"id": "aaaaaaaaaaaa", "title": "Peer review", "title_key": "peer review"}
    si = {
        "id": "bbbbbbbbbbbb",
        "title": "Peer review",
        "title_key": "peer review",
        "doc_role": "supplementary",
    }
    apply_pairing_pass([main, si])
    assert "paired_cache_id" not in main and "paired_cache_id" not in si


def test_delete_by_a_short_title_removes_nothing(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(pc, "cache_root", lambda: tmp_path / "papers")
    a = pc.save_paper_session(_session("REVIEWER COMMENTS"), debone=True, content_hash=H1)
    assert a
    assert pc.delete_cached_paper(title="REVIEWER COMMENTS") is None
    assert _ids() == [a["id"]]
