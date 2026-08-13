# -*- coding: utf-8 -*-
"""design/108 — fail-closed when ingest ends without cache_id."""
from __future__ import annotations

import os
from pathlib import Path

from fastapi.testclient import TestClient

from sentence_reading.api import app as app_mod
from sentence_reading.api.app import app, _finish_job

ROOT = Path(__file__).resolve().parents[1]
DESIGN = ROOT / "docs" / "design" / "108-fail-closed-no-cache.md"
CLIENT = ROOT / "mobile" / "lib" / "api" / "client.dart"


def test_status_version_pin() -> None:
    st = TestClient(app).get("/api/status").json()
    assert st["version"] == "0.3.43"


def test_design_108_exists() -> None:
    assert DESIGN.is_file()
    text = DESIGN.read_text(encoding="utf-8")
    # WHY: chip 108 shipped at 0.3.22 — design pin is historical, not live status.
    assert "0.3.22" in text
    assert "cache" in text.lower()
    assert "fail-closed" in text.lower() or "금지" in text


def test_client_avoids_bare_완료_message() -> None:
    text = CLIENT.read_text(encoding="utf-8")
    assert "design/108" in text
    assert "bareDone" in text or "msg == '완료'" in text


def test_finish_job_still_success_with_cache() -> None:
    jid = "job_finishok0001"
    app_mod._JOBS[jid] = {
        "percent": 90,
        "stage": "save",
        "message": "저장 중",
        "done": False,
        "error": None,
        "result": None,
        "owner_uid": "",
    }
    _finish_job(
        jid,
        {"ok": True, "cache_id": "cache_x", "session_id": "ses_x"},
        message="완료 · 제목으로 보관됨",
    )
    job = app_mod._JOBS[jid]
    assert job["done"] is True
    assert job.get("error") is None
    assert job["result"]["cache_id"] == "cache_x"
    del app_mod._JOBS[jid]


def test_app_source_has_no_cache_error_branch() -> None:
    src = (ROOT / "src" / "sentence_reading" / "api" / "app.py").read_text(
        encoding="utf-8"
    )
    assert "design/108" in src
    assert "keep ingest upload blob" in src or "do not call _finish_job" in src
