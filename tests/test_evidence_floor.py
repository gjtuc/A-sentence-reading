"""design/169g — frozen evidence kinds must remain in allowlist + emit sites."""

from __future__ import annotations

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
    assert EVIDENCE_FLOOR_VERSION == "0.3.130"


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
