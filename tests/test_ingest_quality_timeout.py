# -*- coding: utf-8 -*-
"""design/106 — ingest quality Gemini timeout + GCS progress freshness."""
from __future__ import annotations

import os

from fastapi.testclient import TestClient

from sentence_reading.api.app import app

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DESIGN = os.path.join(ROOT, "docs", "design", "106-ingest-quality-timeout.md")


def test_status_version_pin() -> None:
    with TestClient(app) as client:
        st = client.get("/api/status").json()
    assert st["version"] == "0.3.55"


def test_design_106_exists() -> None:
    assert os.path.isfile(DESIGN)
    text = open(DESIGN, encoding="utf-8").read()
    assert "0.3.20" in text
    assert "90" in text
    assert "timeout" in text.lower() or "타임아웃" in text
    assert "추출 품질" in text or "quality" in text.lower()


def test_call_gemini_has_timeout_constant() -> None:
    debone = open(
        os.path.join(ROOT, "src", "sentence_reading", "llm", "debone.py"),
        encoding="utf-8",
    ).read()
    assert "_GEMINI_TEXT_TIMEOUT_S" in debone
    assert "TimeoutError" in debone
    vision = open(
        os.path.join(ROOT, "src", "sentence_reading", "llm", "vision_ocr.py"),
        encoding="utf-8",
    ).read()
    assert "_GEMINI_VISION_TIMEOUT_S" in vision
