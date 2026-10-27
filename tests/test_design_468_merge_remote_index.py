# -*- coding: utf-8 -*-
"""design/468 — server merge finds papers that are only in the GCS index."""

from __future__ import annotations

import shutil

from sentence_reading.api.supplementary_merge import merge_supplementary
from sentence_reading.cache import paper_cache as pc
from sentence_reading.llm import papers_gcs as pg
from sentence_reading.models import PaperSession, Sentence

_TITLE = "Nickel acetylacetonate catalyst merge remote index fixture title"


def _session(title: str, section: str) -> PaperSession:
    return PaperSession(
        title=title,
        sentences=[
            Sentence(
                id="s-1",
                text="A sentence that is long enough to be kept as body text.",
                section=section,
            )
        ],
        figures=[],
    )


def _fresh_instance(tmp_path, monkeypatch):
    """Analyze both papers on one disk, then serve from an empty one."""
    bucket = tmp_path / "bucket"
    monkeypatch.setattr(pc, "cache_root", lambda: bucket)
    e_main = pc.save_paper_session(
        _session(_TITLE, "introduction"), debone=True, source="pdf", doc_role="main"
    )
    e_si = pc.save_paper_session(
        _session("Supporting Information: " + _TITLE, "supplementary"),
        debone=True,
        source="pdf",
        doc_role="supplementary",
    )
    remote = [dict(e) for e in pc._read_index().get("entries") or []]

    instance = tmp_path / "instance"
    monkeypatch.setattr(pc, "cache_root", lambda: instance)
    pulled: list[str] = []
    uploaded: list[str] = []

    def _download(cid, *, entry=None, **_kw):
        pulled.append(cid)
        shutil.copytree(bucket / cid, instance / cid, dirs_exist_ok=True)
        index = pc._read_index()
        rows = [e for e in index.get("entries") or [] if e.get("id") != cid]
        rows.insert(0, dict(entry or {}, id=cid))
        index["entries"] = rows
        pc._write_index(index)
        return True

    monkeypatch.setattr(pg, "gcs_papers_ready", lambda: True)
    monkeypatch.setattr(pg, "papers_index_object", lambda: "users/u/papers/index.json")
    monkeypatch.setattr(pg, "download_remote_index", lambda: {"entries": remote})
    monkeypatch.setattr(pg, "download_paper_cache", _download)
    monkeypatch.setattr(pg, "upload_paper_cache", lambda cid: uploaded.append(cid) or True)
    return e_main, e_si, pulled, uploaded


def test_merge_on_instance_without_local_index(tmp_path, monkeypatch) -> None:
    e_main, e_si, pulled, uploaded = _fresh_instance(tmp_path, monkeypatch)
    assert pc._read_index().get("entries") in (None, [])

    result = merge_supplementary(str(e_main["id"]))

    assert result.get("ok") is True, result
    assert int(result.get("sentence_count") or 0) == 2
    assert set(pulled) == {e_main["id"], e_si["id"]}
    assert set(uploaded) == {e_main["id"], e_si["id"]}
    by_id = {e["id"]: e for e in pc._read_index().get("entries") or []}
    assert by_id[e_main["id"]].get("doc_role") == "merged"
    assert by_id[e_si["id"]].get("hidden_in_library") is True


def test_merge_without_gcs_still_reads_local_only(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(pc, "cache_root", lambda: tmp_path / "papers")
    monkeypatch.setattr(pg, "gcs_papers_ready", lambda: False)
    result = merge_supplementary("abcdef123456")
    assert result.get("error") == "cache_not_found"
