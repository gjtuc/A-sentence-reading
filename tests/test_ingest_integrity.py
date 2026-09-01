# -*- coding: utf-8 -*-
"""design/168b — ingest_integrity T1–T10 log-only checks."""

from __future__ import annotations

import base64
import json
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("ASR_SKIP_ENV_FILE", "1")

from sentence_reading.api.app import app
from sentence_reading.cache import paper_cache as pc
from sentence_reading.llm import ingest_integrity as integ
from sentence_reading.llm import ops_events as oev
from sentence_reading.llm import papers_gcs as pg
from sentence_reading.models import Figure, PaperSession, Sentence

ROOT = Path(__file__).resolve().parents[1]
DESIGN = ROOT / "docs" / "design" / "168-ingest-observability.md"
TINY_PNG = (
    "data:image/png;base64,"
    + base64.b64encode(
        # 1x1 PNG
        bytes.fromhex(
            "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
            "0000000a49444154789c63000100000500010d0a2db40000000049454e44ae426082"
        )
    ).decode("ascii")
)


@pytest.fixture()
def ops_tmp(tmp_path, monkeypatch):
    monkeypatch.setenv("ASR_OPS_EVENTS", "1")
    monkeypatch.setenv("ASR_INGEST_INTEGRITY", "1")
    monkeypatch.setattr(oev, "local_events_path", lambda: tmp_path / "ops_events.jsonl")
    monkeypatch.setattr(oev, "_gcs_events_object", lambda: None)
    return tmp_path


def test_design_mentions_168b() -> None:
    assert DESIGN.is_file()
    text = DESIGN.read_text(encoding="utf-8")
    assert "168b" in text
    assert "ingest_integrity" in text


def test_kill_switch(ops_tmp, monkeypatch) -> None:
    monkeypatch.setenv("ASR_INGEST_INTEGRITY", "0")
    assert integ.ingest_integrity_enabled() is False
    integ.emit_violations(
        [integ.Violation(invariant="T9", code="figures_meta_dropped", details={"session_figures": 12})]
    )
    assert not oev.local_events_path().is_file()


def test_t9_unit() -> None:
    v = integ.check_fig_meta(12, 0)
    assert len(v) == 1
    assert v[0].invariant == "T9"
    assert v[0].code == "figures_meta_dropped"
    assert integ.check_fig_meta(3, 3) == []


def test_t4_t5_unit() -> None:
    payload = {
        "figures": [{"id": "a"}, {"id": "b"}],
        "sentences": [{"id": "s1"}],
    }
    entry = {"figure_count": 0, "sentence_count": 5}
    codes = {x.code for x in integ.check_session_vs_index(payload, entry)}
    assert "figure_count_mismatch" in codes
    assert "sentence_count_mismatch" in codes


def test_t1_t2_unit() -> None:
    v1 = integ.check_job({"done": True, "error": "boom", "result": {"cache_id": "abcd1234ef00"}})
    assert any(x.invariant == "T1" for x in v1)
    v2 = integ.check_job({"done": True, "error": None, "result": {"ok": True}})
    assert any(x.invariant == "T2" for x in v2)


def test_t7_unit() -> None:
    v = integ.check_job(
        {
            "done": True,
            "error": None,
            "result": {"cache_id": "abcd1234ef00", "translate_pending": True},
        }
    )
    assert any(x.invariant == "T7" for x in v)


def test_t8_unit() -> None:
    v = integ.check_partial_vs_status(job_done=False, ingest_status="ok")
    assert len(v) == 1 and v[0].invariant == "T8"
    assert integ.check_partial_vs_status(job_done=True, ingest_status="ok") == []
    assert integ.check_partial_vs_status(job_done=False, ingest_status="partial") == []


def test_t3_unit() -> None:
    entry = {"ingest_status": "ok", "content_hash": "a" * 64}
    job = {"done": False, "content_hash": "a" * 64}
    v = integ.check_index_vs_job(entry, job)
    assert len(v) == 1 and v[0].invariant == "T3"
    assert integ.check_index_vs_job(entry, {"done": True, "content_hash": "a" * 64}) == []


def test_status_ingest_integrity_pin(ops_tmp) -> None:
    st = TestClient(app).get("/api/status").json()
    assert st["version"] == "0.3.125"
    assert st.get("ingest_integrity") is True
    assert st.get("ops_events") is True


def test_save_hook_keeps_stub_figures(ops_tmp, monkeypatch) -> None:
    """design/168f T9 — empty image_src still gets fig_meta rows."""
    monkeypatch.setattr(pc, "cache_root", lambda: ops_tmp / "papers")
    title = "Ni Cu MDR integrity fixture title long enough xx"
    session = PaperSession(
        title=title,
        sentences=[
            Sentence(id="s-1", text="Enough length for a real sentence here.", section="introduction")
        ],
        figures=[
            Figure(id="fig-0001", image_src="", caption="a"),
            Figure(id="fig-0002", image_src="", caption="b"),
            Figure(id="fig-0003", image_src=TINY_PNG, caption="c"),
        ],
    )
    entry = pc.save_paper_session(session, debone=True, source="pdf")
    assert entry is not None
    assert entry["figure_count"] == 3
    loaded = pc.load_cached_session(entry["id"], load_images=False)
    assert loaded is not None
    sess, _info = loaded
    assert len(sess.figures) == 3
    rows = oev.list_events(limit=50)
    viol = [r for r in rows if r.get("kind") == "consistency_violation"]
    invs = {str((r.get("details") or {}).get("invariant") or "") for r in viol}
    assert "t9" not in invs


def test_emit_violations_round_trip(ops_tmp) -> None:
    integ.emit_violations(
        [
            integ.Violation(
                invariant="T9",
                code="figures_meta_dropped",
                details={"session_figures": 12, "fig_meta": 0},
            )
        ],
        cache_id="abcd1234ef00",
        job_id="job_abc123def456",
    )
    rows = oev.list_events(limit=5)
    assert rows[0]["kind"] == "consistency_violation"
    assert rows[0]["details"]["invariant"] == "t9"
    assert rows[0]["details"]["code"] == "figures_meta_dropped"
    assert rows[0]["details"]["session_figures"] == 12


def test_merge_session_richer_emit(ops_tmp, monkeypatch) -> None:
    root = ops_tmp / "papers"
    root.mkdir()
    monkeypatch.setattr(pg, "cache_root", lambda: root)
    monkeypatch.setattr(pc, "cache_root", lambda: root)
    store: dict[str, bytes] = {}

    def up(name, data, content_type="application/octet-stream"):
        store[name] = bytes(data)
        return True

    def down(name):
        return store.get(name)

    monkeypatch.setattr(pg, "upload_bytes", up)
    monkeypatch.setattr(pg, "download_bytes", down)
    monkeypatch.setattr(pg, "gcs_client_ready", lambda: (True, "ok"))
    monkeypatch.setattr(
        pg,
        "gcs_config",
        lambda: type("C", (), {"enabled": True, "bucket": "b", "prefix": "asr"})(),
    )
    monkeypatch.setenv("ASR_GCS_BUCKET", "b")
    monkeypatch.setenv("ASR_GCS_PREFIX", "asr")

    cid = "abcd1234ef00"
    paper = root / cid
    (paper / "figures").mkdir(parents=True)
    local = {
        "version": 1,
        "title": "Merge Richer Title Long Enough Here",
        "sentences": [{"id": "s1", "text": "Hi."}],
        "figures": [],
        "references": [],
    }
    remote = {
        "version": 1,
        "title": "Merge Richer Title Long Enough Here",
        "sentences": [{"id": "s1", "text": "Hi."}],
        "figures": [
            {"id": "fig-0001", "caption": "", "file": "figures/fig-0001.png"},
            {"id": "fig-0002", "caption": "", "file": "figures/fig-0002.png"},
        ],
        "references": [],
    }
    (paper / "session.json").write_text(json.dumps(local), encoding="utf-8")
    store[f"asr/papers/{cid}/session.json"] = (
        json.dumps(remote, ensure_ascii=False).encode("utf-8")
    )
    assert pg.upload_paper_cache(cid) is True
    kinds = [r["kind"] for r in oev.list_events(limit=20)]
    assert "merge_session_richer" in kinds
