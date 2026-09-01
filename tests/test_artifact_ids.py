"""design/169i — artifact hash/locator helpers + emit kinds."""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("ASR_SKIP_ENV_FILE", "1")

from sentence_reading.llm import artifact_ids as aid
from sentence_reading.llm import evidence_bus as eb
from sentence_reading.llm.evidence_floor import EVIDENCE_FLOOR_VERSION, FROZEN_KINDS
from sentence_reading.llm.evidence_kinds import ALLOWED_KINDS


@pytest.fixture()
def ev_tmp(tmp_path, monkeypatch):
    monkeypatch.setenv("ASR_EVIDENCE_BUS", "1")
    monkeypatch.setattr(eb, "local_events_path", lambda: tmp_path / "evidence.jsonl")
    monkeypatch.setattr(eb, "_gcs_events_object", lambda: None)
    monkeypatch.setattr(eb, "_RATE_MEM", {})
    return tmp_path


def test_artifact_kinds_in_allowlist_and_floor() -> None:
    for k in (
        "artifact_observe",
        "artifact_transfer",
        "artifact_derive",
        "artifact_invalidate",
    ):
        assert k in ALLOWED_KINDS
        assert k in FROZEN_KINDS


def test_floor_version_includes_169i() -> None:
    assert EVIDENCE_FLOOR_VERSION == "0.3.134"


def test_hash16_and_locators() -> None:
    h = aid.hash16(b"hello")
    assert len(h) == 16
    assert aid.hash16(b"hello") == h
    assert aid.locator_local_session("abcd1234ef00").endswith("/session.json")
    assert aid.locator_gcs_session("abcd1234ef00").startswith("gcs:papers/")
    assert aid.artifact_id_session("abcd1234ef00", 2) == "art_sess_abcd1234ef00_2"
    assert aid.next_session_gen({"artifact_gen": 3}) == 4
    assert aid.next_session_gen(None) == 1


def test_emit_transfer_and_observe(ev_tmp) -> None:
    tid = aid.emit_artifact_transfer(
        activity="gcs_upload_session",
        from_locator=aid.locator_local_session("abcd1234ef00"),
        to_locator=aid.locator_gcs_session("abcd1234ef00"),
        content_hash="a" * 16,
        bytes_n=12,
        gen=2,
        cache_id="abcd1234ef00",
        job_id="job_abcd1234ef00",
        trace_id="tr_0123456789abcdef",
    )
    assert tid.startswith("xf_")
    aid.emit_artifact_observe(
        locator=aid.locator_local_session("abcd1234ef00"),
        artifact_kind="session_json",
        content_hash="a" * 16,
        bytes_n=12,
        gen=2,
        activity="cache_open",
        cache_id="abcd1234ef00",
    )
    kinds = [r["kind"] for r in eb.list_events(limit=20)]
    assert "artifact_transfer" in kinds
    assert "artifact_observe" in kinds
    row = next(r for r in eb.list_events(limit=20) if r["kind"] == "artifact_transfer")
    assert row["details"]["activity"] == "gcs_upload_session"
    assert row["details"]["content_hash"] == "a" * 16
    assert row.get("trace_id") == "tr_0123456789abcdef"
