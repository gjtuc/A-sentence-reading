# -*- coding: utf-8 -*-
"""design/256 — ingest poll oversized + translate/practice mismatch evidence."""
from __future__ import annotations

from pathlib import Path

from sentence_reading.llm.ingest_jobs_gcs import (
    INGEST_JOB_VIEW_OVERSIZED_BYTES,
    measure_job_view_size,
)
from sentence_reading.llm.ingest_queue_verdict import compute_ingest_queue_verdicts
from sentence_reading.llm.shadowing_chunks import MAX_SENTENCES, build_chunk_plan
from sentence_reading.llm.shadowing_verdict import (
    ShadowingTimeline,
    compute_shadowing_verdicts,
)

ROOT = Path(__file__).resolve().parents[1]
DESIGN = ROOT / "docs/design/256-ingest-poll-oversized-causal-evidence.md"
EV_PY = ROOT / "src/sentence_reading/llm/evidence_kinds.py"
EV_DART = ROOT / "mobile/lib/services/evidence_kinds.dart"
APP = ROOT / "src/sentence_reading/api/app.py"
IJ = ROOT / "src/sentence_reading/llm/ingest_jobs_gcs.py"
SC = ROOT / "src/sentence_reading/llm/shadowing_chunks.py"
CLIENT = ROOT / "mobile/lib/api/client.dart"
CTRL = ROOT / "mobile/lib/state/library_controller.dart"
PUBSPEC = ROOT / "mobile/pubspec.yaml"
CONFIG = ROOT / "mobile/lib/config.dart"
VERDICT = ROOT / "src/sentence_reading/llm/ingest_queue_verdict.py"
TRACK = ROOT / "scripts/track_ingest_queue.py"


def test_design_256_locked() -> None:
    text = DESIGN.read_text(encoding="utf-8")
    assert "0.3.256" in text
    assert "locked" in text.lower()
    assert "ingest_job_view_size" in text
    assert "translate_optout_mismatch" in text
    assert "sentences_over_max" in text
    assert "poll_500_blocks_upload_queue" in text


def test_versions_256() -> None:
    assert 'version="0.3.256"' in APP.read_text(encoding="utf-8")
    assert '"version": "0.3.256"' in APP.read_text(encoding="utf-8")
    assert "0.3.256" in PUBSPEC.read_text(encoding="utf-8")
    assert "0.3.256" in CONFIG.read_text(encoding="utf-8")


def test_kinds_mirrored() -> None:
    for path in (EV_PY, EV_DART):
        text = path.read_text(encoding="utf-8")
        assert "ingest_job_view_size" in text
        assert "translate_optout_mismatch" in text


def test_server_markers() -> None:
    app = APP.read_text(encoding="utf-8")
    assert "ingest_job_view_size" in app
    assert "measure_job_view_size" in app
    assert "sentences_over_max" in SC.read_text(encoding="utf-8")
    assert "sentence_n" in app
    assert "max_n" in app
    assert "measure_job_view_size" in IJ.read_text(encoding="utf-8")


def test_mobile_markers() -> None:
    client = CLIENT.read_text(encoding="utf-8")
    assert "body_bytes" in client
    assert "bodyBytes" in client
    ctrl = CTRL.read_text(encoding="utf-8")
    assert "translate_optout_mismatch" in ctrl
    assert "want_translate" in ctrl
    assert "'job_id': jid" in ctrl or '"job_id": jid' in ctrl


def test_measure_job_view_size_oversized() -> None:
    huge = "data:image/png;base64," + ("A" * (INGEST_JOB_VIEW_OVERSIZED_BYTES + 100))
    job = {
        "result": {
            "cache_id": "c41e6af5edb5",
            "sentence_count": 1044,
            "figure_count": 1,
            "figures": [{"id": "cov-0001", "image_src": huge}],
        }
    }
    size = measure_job_view_size(job)
    assert size["result_present"] == 1
    assert size["data_url_n"] == 1
    assert size["data_url_bytes_sum"] >= INGEST_JOB_VIEW_OVERSIZED_BYTES
    assert size["oversized"] == 1
    assert size["code"] == "result_too_large"
    assert size["sentence_n"] == 1044


def test_measure_job_view_size_small() -> None:
    size = measure_job_view_size({"result": {"cache_id": "abc", "sentence_count": 3}})
    assert size["oversized"] == 0
    assert size["code"] == "ok"
    assert size["sentence_n"] == 3


def test_build_chunk_plan_sentences_over_max(monkeypatch) -> None:
    monkeypatch.setattr(
        "sentence_reading.llm.shadowing_chunks.shadowing_practice_enabled",
        lambda: True,
    )
    rows = [{"id": str(i), "text": f"s{i}"} for i in range(MAX_SENTENCES + 1)]
    try:
        build_chunk_plan(
            uid="user_a_test01",
            cache_id="abcd1234ef",
            sentences=rows,
            resume=False,
        )
        raise AssertionError("expected ValueError")
    except ValueError as exc:
        assert str(exc) == "sentences_over_max"


def test_verdicts_poll_queue_and_mismatch() -> None:
    events = [
        {
            "kind": "ingest_job_view_size",
            "ts": "2026-09-13T10:00:00Z",
            "job_id": "job_aa1a65211b4b",
            "ok": False,
            "code": "result_too_large",
            "details": {"oversized": 1, "est_bytes": 40_000_000},
        },
        {
            "kind": "ingest_poll_terminal",
            "ts": "2026-09-13T10:01:00Z",
            "job_id": "job_aa1a65211b4b",
            "http_status": 500,
            "code": "http_error",
            "details": {"outcome": "http_error", "body_bytes": 0},
        },
        {
            "kind": "upload_queue_blocked",
            "ts": "2026-09-13T10:02:00Z",
            "job_id": "job_aa1a65211b4b",
            "stage": "resumable_draft",
            "details": {"job_id": "job_aa1a65211b4b"},
        },
        {
            "kind": "translate_optout_mismatch",
            "ts": "2026-09-13T10:03:00Z",
            "cache_id": "c41e6af5edb5",
            "details": {
                "want_translate": 0,
                "sentence_n": 1044,
                "ko_sentence_n": 0,
                "ko_missing_n": 1044,
            },
        },
        {
            "kind": "shadowing_chunks_build_done",
            "ts": "2026-09-13T10:04:00Z",
            "cache_id": "c41e6af5edb5",
            "ok": False,
            "code": "sentences_over_max",
            "details": {"error": "sentences_over_max", "sentence_n": 1044, "max_n": 400},
        },
    ]
    v = compute_ingest_queue_verdicts(events)
    assert "job_view_result_too_large" in v
    assert "poll_500_blocks_upload_queue" in v
    assert "translate_optout_empty_ko" in v
    assert "sentences_over_max_blocks_practice" in v


def test_shadowing_verdict_sentences_over_max() -> None:
    tl = ShadowingTimeline.from_events(
        [
            {
                "kind": "shadowing_chunks_build_done",
                "ts": "2026-09-13T10:04:00Z",
                "cache_id": "c41e6af5edb5",
                "ok": False,
                "code": "sentences_over_max",
                "details": {"error": "sentences_over_max", "sentence_n": 1044, "max_n": 400},
            }
        ]
    )
    v = compute_shadowing_verdicts(tl)
    assert "sentences_over_max_blocks_practice" in v
    assert "build_api_fail" in v


def test_track_script_exists() -> None:
    assert VERDICT.is_file()
    assert TRACK.is_file()
    assert "compute_ingest_queue_verdicts" in TRACK.read_text(encoding="utf-8")
