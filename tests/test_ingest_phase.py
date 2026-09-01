# -*- coding: utf-8 -*-
"""design/168c — ingest_phase + ingest_status partial/ok/error."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("ASR_SKIP_ENV_FILE", "1")

from sentence_reading.api.app import app
from sentence_reading.cache import paper_cache as pc
from sentence_reading.llm import ingest_jobs_gcs as ij
from sentence_reading.models import PaperSession, Sentence

ROOT = Path(__file__).resolve().parents[1]
LIB = ROOT / "mobile" / "lib" / "screens" / "library_screen.dart"


@pytest.fixture()
def cache_tmp(tmp_path, monkeypatch):
    monkeypatch.setattr(pc, "cache_root", lambda: tmp_path / "papers")
    return tmp_path


def _session(title: str = "Phase Machine Paper Title Long Enough") -> PaperSession:
    return PaperSession(
        title=title + " " + ("x" * 8),
        sentences=[
            Sentence(
                id="s-1",
                text="Introduction sentence with enough length here.",
                section="introduction",
            )
        ],
        figures=[],
    )


def test_normalize_ingest_status() -> None:
    assert ij.normalize_ingest_status("partial") == "partial"
    assert ij.normalize_ingest_status("OK") == "ok"
    assert ij.normalize_ingest_status("nope") == "ok"


def test_derive_ingest_phase_mapping() -> None:
    assert ij.derive_ingest_phase({"done": False, "stage": "extract"}) == "uploading"
    assert (
        ij.derive_ingest_phase(
            {"done": False, "stage": "ready", "result": {"ok": True, "translate_pending": True}}
        )
        == "translate_pending"
    )
    assert (
        ij.derive_ingest_phase(
            {"done": False, "stage": "ready", "result": {"ok": True, "cache_id": "x"}}
        )
        == "reading_ready"
    )
    assert (
        ij.derive_ingest_phase({"done": False, "stage": "translate", "result": {}})
        == "translate_pending"
    )
    assert ij.derive_ingest_phase({"done": True, "stage": "done"}) == "complete"
    assert ij.derive_ingest_phase({"done": True, "error": "x", "stage": "error"}) == "error"


def test_save_partial_and_ok(cache_tmp) -> None:
    s = _session()
    e1 = pc.save_paper_session(s, debone=True, source="pdf", ingest_status="partial")
    assert e1 is not None
    assert e1["ingest_status"] == "partial"
    entry = pc.get_index_entry(e1["id"])
    assert entry is not None
    assert entry["ingest_status"] == "partial"

    e2 = pc.save_paper_session(s, debone=True, source="pdf", ingest_status="ok")
    assert e2 is not None
    assert e2["id"] == e1["id"]
    assert e2["ingest_status"] == "ok"


def test_serialize_job_trace_and_phase() -> None:
    job = {
        "percent": 90,
        "stage": "translate",
        "message": "ko",
        "done": False,
        "error": None,
        "result": {"ok": True, "translate_pending": True, "cache_id": "abcd1234ef00"},
        "owner_uid": "uid1",
        "content_hash": "a" * 64,
        "filename": "p.pdf",
        "trace_id": "tr_" + ("ab" * 8),
        "want_translate": True,
        "want_shadowing_chunks": False,
        "cancel_requested": False,
    }
    ij.stamp_ingest_phase(job)
    rec = ij.serialize_job_record("job_abc123def456", job)
    assert rec["trace_id"].startswith("tr_")
    assert rec["ingest_phase"] == "translate_pending"

    view = ij.public_job_view("job_abc123def456", job)
    assert view["ingest_phase"] == "translate_pending"
    assert view["trace_id"].startswith("tr_")
    assert view["done"] is False


def test_status_phase_pins() -> None:
    st = TestClient(app).get("/api/status").json()
    assert st["version"] == "0.3.114"
    assert st.get("ingest_phase_machine") is True
    assert st.get("ingest_status_partial") is True
    assert st.get("ingest_integrity") is True


def test_mobile_library_status_chip_pin() -> None:
    text = LIB.read_text(encoding="utf-8")
    assert "부분 저장" in text
    assert "ingestStatus" in text
    assert "_ingestStatusLabel" in text
    assert "design/168c" in text
