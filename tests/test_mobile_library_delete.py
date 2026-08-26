# -*- coding: utf-8 -*-
"""design/102 - mobile library delete + GCS/user purge."""
from __future__ import annotations

import os

from fastapi.testclient import TestClient

from sentence_reading.api import app as app_mod


def test_status_version_pin() -> None:
    with TestClient(app_mod.app) as client:
        st = client.get("/api/status").json()
    assert st["version"] == "0.3.53"


def test_mobile_library_delete_wiring() -> None:
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    screen = open(
        os.path.join(root, "mobile", "lib", "screens", "library_screen.dart"),
        encoding="utf-8",
    ).read()
    client = open(
        os.path.join(root, "mobile", "lib", "api", "client.dart"),
        encoding="utf-8",
    ).read()
    ctrl = open(
        os.path.join(root, "mobile", "lib", "state", "library_controller.dart"),
        encoding="utf-8",
    ).read()
    cache = open(
        os.path.join(root, "src", "sentence_reading", "cache", "paper_cache.py"),
        encoding="utf-8",
    ).read()
    design = open(
        os.path.join(root, "docs", "design", "102-library-delete.md"),
        encoding="utf-8",
    ).read()
    assert "Icons.delete_outline" in screen
    assert "_confirmDelete" in screen
    assert "deletePaper" in client
    assert "deletePapers" in ctrl
    assert "remove_paper_notes" in cache
    assert "delete_chunk_plan" in cache
    assert "delete_takes" in cache
    assert "0.3.16" in design
    pub = open(
        os.path.join(root, "mobile", "pubspec.yaml"), encoding="utf-8"
    ).read()
    assert "0.3.53" in pub


def test_delete_endpoint_has_paid_gate() -> None:
    app_src = open(
        os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "src",
            "sentence_reading",
            "api",
            "app.py",
        ),
        encoding="utf-8",
    ).read()
    # ensure gate is applied near DELETE handler
    idx = app_src.find('def cache_delete(request: Request, cache_id: str)')
    assert idx > 0
    snippet = app_src[idx : idx + 400]
    assert "_paid_access_denied" in snippet
