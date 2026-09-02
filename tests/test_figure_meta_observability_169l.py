# -*- coding: utf-8 -*-
"""design/169l L1/L2 — figure meta save boundary + T11 integrity bus."""

from __future__ import annotations

import base64
import json
import os

import pytest

os.environ.setdefault("ASR_SKIP_ENV_FILE", "1")

from sentence_reading.cache import paper_cache as pc
from sentence_reading.llm import evidence_bus as eb
from sentence_reading.llm import ingest_integrity as integ
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
def papers_ev(tmp_path, monkeypatch):
    monkeypatch.setenv("ASR_EVIDENCE_BUS", "1")
    monkeypatch.setenv("ASR_INGEST_INTEGRITY", "1")
    monkeypatch.setattr(pc, "cache_root", lambda: tmp_path / "papers")
    monkeypatch.setattr(eb, "local_events_path", lambda: tmp_path / "evidence.jsonl")
    monkeypatch.setattr(eb, "_gcs_events_object", lambda: None)
    monkeypatch.setattr(eb, "_RATE_MEM", {})
    return tmp_path


def test_t11_unit() -> None:
    ok_rows = [{"id": "fig-1", "file": "figures/fig-1.png"}]
    assert integ.check_figure_file_rel(ok_rows) == []
    bad_rows = [{"id": "fig-1", "caption": "x"}]
    v = integ.check_figure_file_rel(bad_rows)
    assert len(v) == 1
    assert v[0].invariant == "T11"
    assert v[0].code == "figure_file_rel_missing"
    assert v[0].details["missing_n"] == 1


def test_save_emits_figure_meta_write_ok(papers_ev) -> None:
    title = "Figure meta write ok fixture title long enough x"
    session = PaperSession(
        title=title,
        sentences=[Sentence(id="s1", text="Hello world sentence here ok.")],
        figures=[Figure(id="fig-1", image_src=TINY_PNG, caption="c")],
    )
    entry = pc.save_paper_session(session, debone=True, source="pdf")
    assert entry is not None
    rows = eb.list_events(limit=50)
    writes = [r for r in rows if r.get("kind") == "figure_meta_write"]
    assert len(writes) == 1
    assert writes[0]["ok"] is True
    assert writes[0]["details"]["file_rel_n"] == 1
    assert writes[0]["details"]["activity"] == "ingest_store"


def test_save_stub_emits_incomplete_and_t11_bus(papers_ev) -> None:
    title = "Figure meta incomplete fixture title long enough"
    session = PaperSession(
        title=title,
        sentences=[Sentence(id="s1", text="Hello world sentence here ok.")],
        figures=[
            Figure(id="fig-0001", image_src="", caption="a"),
            Figure(id="fig-0002", image_src="", caption="b"),
        ],
    )
    entry = pc.save_paper_session(session, debone=True, source="pdf")
    assert entry is not None
    rows = eb.list_events(limit=50)
    writes = [r for r in rows if r.get("kind") == "figure_meta_write"]
    assert len(writes) == 1
    assert writes[0]["ok"] is False
    assert writes[0]["code"] == "figure_meta_incomplete"
    assert writes[0]["details"]["missing_file_n"] == 2
    viol = [r for r in rows if r.get("kind") == "ingest_integrity_violation"]
    assert any(r.get("details", {}).get("invariant") == "t11" for r in viol)


def test_translate_resave_regress_and_preserve_skip(papers_ev) -> None:
    title = "Figure meta regress fixture title long enough xx"
    s1 = PaperSession(
        title=title,
        sentences=[Sentence(id="s1", text="Hello world sentence here ok.")],
        figures=[Figure(id="fig-1", image_src=TINY_PNG, caption="c")],
    )
    e1 = pc.save_paper_session(s1, debone=True, source="pdf")
    assert e1 is not None
    cid = e1["id"]
    s2 = PaperSession(
        title=title,
        sentences=[
            Sentence(
                id="s1",
                text="Hello world sentence here ok.",
                text_ko="번역됨",
            )
        ],
        figures=[Figure(id="fig-1", image_src="", caption="c", caption_ko="캡션")],
    )
    # Simulate translate save without prior pull — prior PNG bytes lost.
    import shutil

    shutil.rmtree(pc.cache_root() / cid / "figures", ignore_errors=True)
    e2 = pc.save_paper_session(s2, debone=True, source="pdf")
    assert e2 is not None
    rows = eb.list_events(limit=100)
    regress = [r for r in rows if r.get("kind") == "figure_meta_regress"]
    assert len(regress) >= 1
    assert regress[-1]["details"]["prev_file_rel_n"] == 1
    assert regress[-1]["details"]["new_file_rel_n"] == 0
    skips = [r for r in rows if r.get("kind") == "figure_preserve_skip"]
    assert len(skips) == 0  # prior_png_n==0 after rmtree — skip needs prior bytes unused


def test_save_preserves_prior_meta_file_via_gcs(papers_ev, monkeypatch) -> None:
    """design/169l — prior session meta file rel + GCS pull when local bytes gone."""
    title = "Preserve prior meta gcs fixture title long enough"
    s1 = PaperSession(
        title=title,
        sentences=[Sentence(id="s1", text="Hello world sentence here ok.")],
        figures=[Figure(id="fig-1", image_src=TINY_PNG, caption="c")],
    )
    e1 = pc.save_paper_session(s1, debone=True, source="pdf")
    assert e1 is not None
    cid = e1["id"]
    import shutil

    shutil.rmtree(pc.cache_root() / cid / "figures", ignore_errors=True)
    tiny = base64.b64decode(TINY_PNG.split(",", 1)[1])

    def _ensure(cache_id: str, rel: str):
        assert cache_id == cid
        assert rel == "figures/fig-1.png"
        dest = pc.cache_root() / cid / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(tiny)
        return dest, "ok"

    monkeypatch.setattr(
        "sentence_reading.llm.papers_gcs.ensure_figure_local_with_reason",
        _ensure,
    )
    s2 = PaperSession(
        title=title,
        sentences=[
            Sentence(id="s1", text="Hello world sentence here ok.", text_ko="ko")
        ],
        figures=[Figure(id="fig-1", image_src="", caption="c", caption_ko="캡션")],
    )
    e2 = pc.save_paper_session(s2, debone=True, source="pdf")
    assert e2 is not None
    meta = json.loads((pc.cache_root() / cid / "session.json").read_text(encoding="utf-8"))
    assert meta["figures"][0].get("file") == "figures/fig-1.png"
    rows = eb.list_events(limit=50)
    writes = [r for r in rows if r.get("kind") == "figure_meta_write"]
    assert writes[-1]["ok"] is True
    assert writes[-1]["details"]["file_rel_n"] == 1


def test_emit_violations_promotes_to_evidence_bus(papers_ev) -> None:
    integ.emit_violations(
        [
            integ.Violation(
                invariant="T11",
                code="figure_file_rel_missing",
                details={"figure_n": 2, "file_rel_n": 0, "missing_n": 2},
            )
        ],
        cache_id="abcd1234ef00",
    )
    rows = eb.list_events(limit=5)
    assert rows[0]["kind"] == "ingest_integrity_violation"
    assert rows[0]["details"]["invariant"] == "t11"
    assert rows[0]["code"] == "figure_file_rel_missing"
