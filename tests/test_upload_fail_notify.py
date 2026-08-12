# -*- coding: utf-8 -*-
"""design/105 — upload fail notification + 20m ingest poll."""
from __future__ import annotations

import os
import re

from fastapi.testclient import TestClient

from sentence_reading.api.app import app

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MOBILE = os.path.join(ROOT, "mobile")
DESIGN = os.path.join(ROOT, "docs", "design", "105-upload-fail-notify.md")


def test_status_version_pin() -> None:
    with TestClient(app) as client:
        st = client.get("/api/status").json()
    assert st["version"] == "0.3.31"
    assert st.get("mobile_upload_background") is True


def test_design_105_exists() -> None:
    assert os.path.isfile(DESIGN)
    text = open(DESIGN, encoding="utf-8").read()
    assert "0.3.19" in text
    assert "업로드 실패" in text or "showFailed" in text
    assert "20" in text


def test_show_failed_posts_result_notify() -> None:
    notify = open(
        os.path.join(MOBILE, "lib", "api", "upload_notify.dart"),
        encoding="utf-8",
    ).read()
    assert "showUploadFailed" in notify
    assert "await stop()" in notify
    # Must not be stop-only anymore for the primary path
    assert "design/105" in notify
    main = open(
        os.path.join(
            MOBILE,
            "android",
            "app",
            "src",
            "main",
            "kotlin",
            "com",
            "gjtuc",
            "sentence_reading",
            "MainActivity.kt",
        ),
        encoding="utf-8",
    ).read()
    assert "showUploadFailed" in main
    svc = open(
        os.path.join(
            MOBILE,
            "android",
            "app",
            "src",
            "main",
            "kotlin",
            "com",
            "gjtuc",
            "sentence_reading",
            "UploadForegroundService.kt",
        ),
        encoding="utf-8",
    ).read()
    assert "asr_upload_result" in svc
    assert "RESULT_NOTIF_ID" in svc or "74102" in svc
    assert "IMPORTANCE_DEFAULT" in svc
    assert "fun showFailed" in svc


def test_poll_timeout_20_minutes() -> None:
    client = open(
        os.path.join(MOBILE, "lib", "api", "client.dart"),
        encoding="utf-8",
    ).read()
    assert "Duration(minutes: 20)" in client
    assert "minutes: 12)" not in client or client.count("minutes: 20)") >= 2
    ctrl = open(
        os.path.join(MOBILE, "lib", "state", "library_controller.dart"),
        encoding="utf-8",
    ).read()
    assert "statusCode == 504" in ctrl
    assert "showFailed" in ctrl


def test_pubspec_pin() -> None:
    pub = open(os.path.join(MOBILE, "pubspec.yaml"), encoding="utf-8").read()
    assert "0.3.31" in pub


def test_no_secrets() -> None:
    banned = re.compile(
        r"(AIza[0-9A-Za-z_-]{20,}|BEGIN (RSA |EC )?PRIVATE KEY|"
        r"GEMINI_API_KEY|client_secret|private_key)",
        re.I,
    )
    for rel in (
        "lib/api/upload_notify.dart",
        "lib/api/client.dart",
        "lib/state/library_controller.dart",
        "android/app/src/main/kotlin/com/gjtuc/sentence_reading/UploadForegroundService.kt",
        "android/app/src/main/kotlin/com/gjtuc/sentence_reading/MainActivity.kt",
    ):
        text = open(os.path.join(MOBILE, rel), encoding="utf-8").read()
        assert banned.search(text) is None, rel
