# -*- coding: utf-8 -*-
"""design/168f — fig_meta stubs, patch_index fix, count sync."""

from __future__ import annotations

import base64
import os

import pytest

os.environ.setdefault("ASR_SKIP_ENV_FILE", "1")

from sentence_reading.cache import paper_cache as pc
from sentence_reading.models import Figure, PaperSession, Sentence

TINY_PNG = (
    "data:image/png;base64,"
    + base64.b64encode(
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01"
        b"\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx"
        b"\x9cc\xf8\x0f\x00\x00\x01\x01\x00\x05\x18\xd8N\x00\x00\x00\x00IEND"
        b"\xaeB`\x82"
    ).decode("ascii")
)


@pytest.fixture()
def papers(tmp_path, monkeypatch):
    monkeypatch.setattr(pc, "cache_root", lambda: tmp_path / "papers")
    return tmp_path / "papers"


def test_patch_index_entry_applies_fields(papers) -> None:
    title = "Patch index entry fixture title long enough xxx"
    session = PaperSession(
        title=title,
        sentences=[Sentence(id="s1", text="Hello world sentence here ok.")],
        figures=[Figure(id="fig-1", image_src=TINY_PNG, caption="c")],
    )
    entry = pc.save_paper_session(session, debone=True, source="pdf", ingest_status="ok")
    assert entry is not None
    cid = entry["id"]
    patched = pc.patch_index_entry(cid, ingest_status="error", figure_count=99)
    assert patched is not None
    assert patched["ingest_status"] == "error"
    assert patched["figure_count"] == 99
    again = pc.get_index_entry(cid)
    assert again is not None
    assert again["ingest_status"] == "error"
    assert again["figure_count"] == 99


def test_sync_index_counts_from_session(papers) -> None:
    title = "Sync counts fixture title long enough for key xx"
    session = PaperSession(
        title=title,
        sentences=[
            Sentence(id="s1", text="Hello world sentence here ok."),
            Sentence(id="s2", text="Second sentence for count check."),
        ],
        figures=[
            Figure(id="fig-1", image_src="", caption="a"),
            Figure(id="fig-2", image_src=TINY_PNG, caption="b"),
        ],
    )
    entry = pc.save_paper_session(session, debone=True, source="pdf")
    assert entry is not None
    cid = entry["id"]
    # Corrupt index counts (historical Ni/Cu shape).
    pc.patch_index_entry(cid, figure_count=0, sentence_count=0)
    fixed = pc.sync_index_counts_from_session(cid)
    assert fixed is not None
    assert fixed["figure_count"] == 2
    assert fixed["sentence_count"] == 2


def test_save_preserves_prior_png_on_empty_src(papers) -> None:
    title = "Preserve prior png fixture title long enough xx"
    s1 = PaperSession(
        title=title,
        sentences=[Sentence(id="s1", text="Hello world sentence here ok.")],
        figures=[Figure(id="fig-1", image_src=TINY_PNG, caption="c")],
    )
    e1 = pc.save_paper_session(s1, debone=True, source="pdf")
    assert e1 is not None
    cid = e1["id"]
    # Re-save with empty src (lazy open shape) — must keep PNG + meta.
    s2 = PaperSession(
        title=title,
        sentences=[Sentence(id="s1", text="Hello world sentence here ok.")],
        figures=[Figure(id="fig-1", image_src="", caption="c")],
    )
    e2 = pc.save_paper_session(s2, debone=True, source="pdf")
    assert e2 is not None
    assert e2["id"] == cid
    assert e2["figure_count"] == 1
    loaded = pc.load_cached_session(cid, load_images=True)
    assert loaded is not None
    sess, _ = loaded
    assert len(sess.figures) == 1
    assert sess.figures[0].image_src.startswith("data:")
