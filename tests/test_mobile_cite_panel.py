# -*- coding: utf-8 -*-
"""design/148 — mobile References panel status flag."""
from __future__ import annotations

import os

from fastapi.testclient import TestClient

from sentence_reading.api import app as app_mod
from sentence_reading.api.app import app


def test_status_mobile_cite_ref_panel_default() -> None:
    st = TestClient(app).get("/api/status").json()
    assert st["version"] == "0.3.82"
    assert st["mobile_cite_ref_panel"] is True
    assert st["cite_ref_open"] is True


def test_status_mobile_cite_ref_panel_kill() -> None:
    prev = os.environ.get("ASR_MOBILE_CITE_REF_PANEL")
    os.environ["ASR_MOBILE_CITE_REF_PANEL"] = "0"
    try:
        st = TestClient(app_mod.app).get("/api/status").json()
        assert st["mobile_cite_ref_panel"] is False
    finally:
        if prev is None:
            os.environ.pop("ASR_MOBILE_CITE_REF_PANEL", None)
        else:
            os.environ["ASR_MOBILE_CITE_REF_PANEL"] = prev


def test_design_148_doc() -> None:
    from pathlib import Path

    text = (
        Path(__file__).resolve().parents[1]
        / "docs"
        / "design"
        / "148-mobile-cite-panel.md"
    ).read_text(encoding="utf-8")
    assert "0.3.69" in text
    assert "mobile_cite_ref_panel" in text
    assert "stripCiteMarkersForDisplay" in text or "stripped" in text
