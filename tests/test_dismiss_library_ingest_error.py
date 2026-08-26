# -*- coding: utf-8 -*-
"""design/109 — dismiss sticky library ingest error + clear terminal draft."""
from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from sentence_reading.api.app import app

ROOT = Path(__file__).resolve().parents[1]
DESIGN = ROOT / "docs" / "design" / "109-dismiss-library-ingest-error.md"
CLIENT = ROOT / "mobile" / "lib" / "api" / "client.dart"
CTRL = ROOT / "mobile" / "lib" / "state" / "library_controller.dart"
SCREEN = ROOT / "mobile" / "lib" / "screens" / "library_screen.dart"
PUB = ROOT / "mobile" / "pubspec.yaml"


def test_status_version_pin() -> None:
    st = TestClient(app).get("/api/status").json()
    assert st["version"] == "0.3.65"


def test_design_109_exists() -> None:
    assert DESIGN.is_file()
    text = DESIGN.read_text(encoding="utf-8")
    assert "0.3.23" in text
    assert "dismissError" in text or "닫기" in text
    assert "422" in text


def test_client_terminal_empty_cache_is_422() -> None:
    text = CLIENT.read_text(encoding="utf-8")
    assert "design/109" in text
    # Terminal done-without-library must not look like a retryable 5xx.
    assert "422" in text
    assert "제목이 너무 짧은 PDF일 수 있습니다" in text


def test_controller_clears_draft_on_422_and_dismiss() -> None:
    text = CTRL.read_text(encoding="utf-8")
    assert "design/109" in text
    assert "dismissError" in text
    assert "e.statusCode == 422" in text
    assert "_drafts.clear()" in text


def test_library_screen_has_dismiss_button() -> None:
    text = SCREEN.read_text(encoding="utf-8")
    assert "dismissError" in text
    assert "닫기" in text


def test_pubspec_version() -> None:
    assert "0.3.65" in PUB.read_text(encoding="utf-8")
