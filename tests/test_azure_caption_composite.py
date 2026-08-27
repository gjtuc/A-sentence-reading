# -*- coding: utf-8 -*-
"""design/149 — figure caption in composite PNG contract."""
from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from sentence_reading.api.app import app

ROOT = Path(__file__).resolve().parents[1]


def test_design_149_doc() -> None:
    text = (ROOT / "docs" / "design" / "149-azure-caption-composite.md").read_text(
        encoding="utf-8"
    )
    assert "0.3.70" in text
    assert "figure_caption_in_image" in text
    assert "resolve_figure_caption" in text


def test_mobile_reader_hides_caption_when_flag() -> None:
    src = (ROOT / "mobile" / "lib" / "screens" / "reader_screen.dart").read_text(
        encoding="utf-8"
    )
    assert "figureCaptionInImage" in src
    assert "!figureCaptionInImage" in src


def test_web_app_hides_figure_caption() -> None:
    js = (ROOT / "src" / "sentence_reading" / "static" / "app.js").read_text(
        encoding="utf-8"
    )
    assert "figureCaptionInImageEnabled" in js
    assert "hideCaptionUnderImage" in js


def test_status_figure_caption_flags() -> None:
    st = TestClient(app).get("/api/status").json()
    assert st["figure_caption_in_image"] is True
    assert st["mobile_figure_caption_in_image"] is True
