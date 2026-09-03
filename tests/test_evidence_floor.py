"""design/169g — frozen evidence kinds must remain in allowlist + emit sites."""

from __future__ import annotations

import json
import os

import pytest

os.environ.setdefault("ASR_SKIP_ENV_FILE", "1")

from sentence_reading.llm import evidence_bus as eb
from sentence_reading.llm.evidence_floor import (
    EVIDENCE_FLOOR_VERSION,
    FROZEN_KINDS,
    verify_evidence_floor,
)
from sentence_reading.llm.evidence_kinds import ALLOWED_KINDS


@pytest.fixture()
def ev_tmp(tmp_path, monkeypatch):
    monkeypatch.setenv("ASR_EVIDENCE_BUS", "1")
    monkeypatch.setattr(eb, "local_events_path", lambda: tmp_path / "evidence.jsonl")
    monkeypatch.setattr(eb, "_gcs_events_object", lambda: None)
    monkeypatch.setattr(eb, "_RATE_MEM", {})
    return tmp_path


def test_frozen_kinds_subset_of_allowlist() -> None:
    missing = sorted(FROZEN_KINDS - ALLOWED_KINDS)
    assert missing == [], missing


def test_verify_evidence_floor_clean() -> None:
    errs = verify_evidence_floor()
    assert errs == [], errs


def test_floor_version_pin() -> None:
    assert EVIDENCE_FLOOR_VERSION == "0.3.145"


def test_gemini_timed_emits_start_and_done(ev_tmp, monkeypatch) -> None:
    """design/169g phase 1 — digest/harmonize blind fixed via start/done."""
    import sentence_reading.llm.translate_section as ts

    monkeypatch.setattr(
        ts.tr,
        "_gemini_generate",
        lambda _system, _user: "EN: ok\nKO: 확인",
    )
    out = ts._gemini_timed("digest", "sys", "user text")
    assert out and "KO" in out
    kinds = [r["kind"] for r in eb.list_events(limit=20)]
    assert "translate_call_start" in kinds
    assert "translate_call_done" in kinds
    rows = [r for r in eb.list_events(limit=20) if r["kind"] == "translate_call_start"]
    assert rows[0]["details"]["call_kind"] == "digest"


def test_emit_handoff_snake_stages(ev_tmp) -> None:
    import sentence_reading.llm.translate_section as ts

    hid = ts._emit_handoff(
        from_stage="google_batch",
        to_stage="gemini_digest",
        section="title",
        in_n=1,
        out_n=1,
    )
    assert hid.startswith("hf_")
    rows = [r for r in eb.list_events(limit=10) if r["kind"] == "handoff"]
    assert rows
    d = rows[0]["details"]
    assert d["from_stage"] == "google_batch"
    assert d["to_stage"] == "gemini_digest"
    assert d["section"] == "title"
    assert d["in_n"] == 1
    assert d["handoff_id"].startswith("hf_")


def test_lifecycle_emit_handoff(ev_tmp) -> None:
    """design/169g phase 4 — shared emit_handoff for upload/open/delete edges."""
    hid = eb.emit_handoff(
        from_stage="client_upload",
        to_stage="ingest_started",
        job_id="job_abcd1234ef00",
        stage="queued",
        in_n=12,
    )
    assert hid.startswith("hf_")
    rows = [r for r in eb.list_events(limit=10) if r["kind"] == "handoff"]
    assert rows
    d = rows[0]["details"]
    assert d["from_stage"] == "client_upload"
    assert d["to_stage"] == "ingest_started"
    assert d["in_n"] == 12
    assert d["handoff_id"] == hid


def test_translate_call_carries_trace_id(ev_tmp, monkeypatch) -> None:
    """design/169g phase 5 — job trace_id on translate call_* evidence."""
    import sentence_reading.llm.translate_section as ts

    monkeypatch.setattr(
        ts.tr,
        "_gemini_generate",
        lambda _system, _user: "EN: ok\nKO: 확인",
    )
    ts._EVIDENCE_CTX.job_id = "job_abcd1234ef00"
    ts._EVIDENCE_CTX.cache_id = "cid1"
    ts._EVIDENCE_CTX.owner_uid = ""
    ts._EVIDENCE_CTX.trace_id = "tr_0123456789abcdef"
    try:
        out = ts._gemini_timed("digest", "sys", "user text")
        assert out and "KO" in out
        rows = [
            r
            for r in eb.list_events(limit=20)
            if r["kind"] == "translate_call_start"
        ]
        assert rows
        assert rows[0].get("trace_id") == "tr_0123456789abcdef"
    finally:
        ts._EVIDENCE_CTX.job_id = ""
        ts._EVIDENCE_CTX.cache_id = ""
        ts._EVIDENCE_CTX.owner_uid = ""
        ts._EVIDENCE_CTX.trace_id = ""


def test_evidence_retention_filter_and_rotate(ev_tmp, monkeypatch) -> None:
    """design/169g phase 6 — drop rows older than keep_days."""
    from datetime import datetime, timedelta, timezone

    monkeypatch.setenv("ASR_EVIDENCE_RETENTION_DAYS", "7")
    now = datetime(2026, 9, 1, 12, 0, 0, tzinfo=timezone.utc)
    old_ts = (now - timedelta(days=10)).strftime("%Y-%m-%dT%H:%M:%SZ")
    new_ts = (now - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
    rows = [
        {"id": "ev_old", "ts": old_ts, "kind": "handoff"},
        {"id": "ev_new", "ts": new_ts, "kind": "handoff"},
    ]
    kept, dropped = eb.filter_retained(rows, keep_days=7, now=now)
    assert dropped == 1
    assert [r["id"] for r in kept] == ["ev_new"]
    # Persist then rotate
    path = eb.local_events_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(eb, "_LAST_ROTATE_MONO", 0.0)
    stats = eb.rotate_events(keep_days=7, force=True)
    assert stats["ok"] is True
    assert stats["dropped"] == 1
    assert stats["after"] == 1
    left = eb.list_events(limit=10)
    assert len(left) == 1
    assert left[0]["id"] == "ev_new"


def test_bind_evidence_ctx_on_worker_thread(ev_tmp, monkeypatch) -> None:
    """design/169h H0 — worker thread emit keeps job/trace ids."""
    import concurrent.futures

    import sentence_reading.llm.translate_section as ts

    monkeypatch.setattr(
        ts.tr,
        "_gemini_generate",
        lambda _system, _user: "EN: ok\nKO: 확인",
    )

    def _worker() -> None:
        # Simulate empty local before bind (fresh thread).
        assert not getattr(ts._EVIDENCE_CTX, "job_id", "")
        ts._bind_evidence_ctx(
            "job_abcd1234ef00",
            "cid1",
            "",
            "tr_0123456789abcdef",
            section="title",
        )
        ts._gemini_timed("harmonize", "sys", "user")

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        pool.submit(_worker).result(timeout=10)

    rows = [
        r for r in eb.list_events(limit=20) if r["kind"] == "translate_call_start"
    ]
    assert rows
    assert rows[0].get("job_id") == "job_abcd1234ef00"
    assert rows[0].get("trace_id") == "tr_0123456789abcdef"
    assert rows[0]["details"].get("call_kind") == "harmonize"


def test_emit_checkpoint_tokens(ev_tmp) -> None:
    """design/169h H1 — interior checkpoint kind."""
    import sentence_reading.llm.translate_section as ts

    ts._emit_checkpoint(
        "harmonize_pool_end",
        section="title",
        in_n=3,
        out_n=3,
        job_id="job_abcd1234ef00",
        cache_id="cid1",
        trace_id="tr_0123456789abcdef",
    )
    rows = [r for r in eb.list_events(limit=10) if r["kind"] == "checkpoint"]
    assert rows
    d = rows[0]["details"]
    assert d["checkpoint"] == "harmonize_pool_end"
    assert d["section"] == "title"
    assert d["in_n"] == 3
    assert rows[0].get("job_id") == "job_abcd1234ef00"
    assert rows[0].get("trace_id") == "tr_0123456789abcdef"
