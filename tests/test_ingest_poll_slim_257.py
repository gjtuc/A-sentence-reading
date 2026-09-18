# -*- coding: utf-8 -*-
"""design/257 — slim ingest poll + practice cap + translate hydrate honesty."""
from __future__ import annotations

from pathlib import Path

from sentence_reading.llm.ingest_jobs_gcs import (
    INGEST_JOB_VIEW_OVERSIZED_BYTES,
    measure_job_view_size,
    public_job_view,
    slim_job_result_for_poll,
)
from sentence_reading.llm.shadowing_chunks import MAX_SENTENCES
from asr_versions import app_version

ROOT = Path(__file__).resolve().parents[1]
DESIGN = ROOT / "docs/design/257-ingest-poll-slim-practice-cap.md"
APP = ROOT / "src/sentence_reading/api/app.py"
IJ = ROOT / "src/sentence_reading/llm/ingest_jobs_gcs.py"
SC = ROOT / "src/sentence_reading/llm/shadowing_chunks.py"
CTRL = ROOT / "mobile/lib/state/library_controller.dart"
READER = ROOT / "mobile/lib/screens/reader_screen.dart"
PUBSPEC = ROOT / "mobile/pubspec.yaml"
CONFIG = ROOT / "mobile/lib/config.dart"


def test_design_257_locked() -> None:
    text = DESIGN.read_text(encoding="utf-8")
    assert "0.3.257" in text
    assert "locked" in text.lower()
    assert "slim_job_result_for_poll" in text or "include_images=False" in text
    assert "2000" in text


def test_versions_257() -> None:
    # design/257 shipped at 0.3.257; later chips may bump further.
    app = APP.read_text(encoding="utf-8")
    assert f'version="{app_version()}"' in app
    assert "0.3." in PUBSPEC.read_text(encoding="utf-8")
    assert "0.3." in CONFIG.read_text(encoding="utf-8")


def test_markers() -> None:
    assert "slim_job_result_for_poll" in IJ.read_text(encoding="utf-8")
    assert "include_images=False" in APP.read_text(encoding="utf-8")
    assert "MAX_SENTENCES = 2000" in SC.read_text(encoding="utf-8") or "_MAX_SENTENCES = 2000" in SC.read_text(
        encoding="utf-8"
    )
    assert MAX_SENTENCES == 2000
    ctrl = CTRL.read_text(encoding="utf-8")
    assert "hydrate must not force translate=0" in ctrl or "design/257" in ctrl
    assert "_hydrateActive.isNotEmpty" not in ctrl or "design/257" in ctrl
    # hydrate short-circuit removed
    assert "if (_hydrateActive.isNotEmpty) {\n      return false;" not in ctrl
    reader = READER.read_text(encoding="utf-8")
    assert "shadowingChunksCacheId == s.cacheId" in reader


def test_slim_strips_data_urls() -> None:
    huge = "data:image/png;base64," + ("B" * (INGEST_JOB_VIEW_OVERSIZED_BYTES + 50))
    raw = {
        "cache_id": "c41e6af5edb5",
        "session_id": "ses_abc",
        "title": "t",
        "sentence_count": 1044,
        "figure_count": 21,
        "translate_pending": True,
        "sentences": [{"id": "0", "text": "hello"}],
        "figure": {"id": "cov-0001", "image_src": huge},
        "figures": [{"id": "fig-0002", "image_src": huge}],
        "shadowing_chunks": {"status": "skipped", "error": "deferred_post_handoff"},
    }
    slim = slim_job_result_for_poll(raw)
    assert slim["cache_id"] == "c41e6af5edb5"
    assert slim["session_id"] == "ses_abc"
    assert slim["translate_pending"] is True
    assert slim["figure"]["image_src"] == ""
    assert slim["figures"][0]["image_src"] == ""
    assert slim["sentences"][0]["text"] == "hello"
    assert slim["shadowing_chunks"]["status"] == "skipped"
    view = public_job_view(
        "job_aa1a65211b4b",
        {"done": True, "percent": 100, "result": raw, "ingest_phase": "complete"},
    )
    assert view["done"] is True
    assert view["cache_id"] == "c41e6af5edb5"
    assert view["translate_pending"] is True  # preserved from result
    assert view["figure"]["image_src"] == ""
    size = measure_job_view_size({"result": view})
    assert size["data_url_n"] == 0
    assert size["oversized"] == 0
