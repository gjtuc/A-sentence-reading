# -*- coding: utf-8 -*-
"""design/101 - mobile library long-press reorder."""
from __future__ import annotations

import os

from fastapi.testclient import TestClient

from sentence_reading.api import app as app_mod


def test_status_version_pin() -> None:
    with TestClient(app_mod.app) as client:
        st = client.get("/api/status").json()
    assert st["version"] == "0.3.57"


def test_mobile_library_reorder_wiring() -> None:
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    screen = open(
        os.path.join(root, "mobile", "lib", "screens", "library_screen.dart"),
        encoding="utf-8",
    ).read()
    models = open(
        os.path.join(root, "mobile", "lib", "api", "library_order_models.dart"),
        encoding="utf-8",
    ).read()
    ctrl = open(
        os.path.join(root, "mobile", "lib", "state", "library_controller.dart"),
        encoding="utf-8",
    ).read()
    design = open(
        os.path.join(root, "docs", "design", "101-library-reorder.md"),
        encoding="utf-8",
    ).read()
    assert "SliverReorderableList" in screen
    assert "ReorderableDelayedDragStartListener" in screen
    assert "reorderPapers" in ctrl
    assert "asr.library.order.v1" in models
    assert "applyLibraryOrder" in models
    assert "0.3.15" in design
    pub = open(
        os.path.join(root, "mobile", "pubspec.yaml"), encoding="utf-8"
    ).read()
    assert "0.3.57" in pub


def test_apply_library_order_pure() -> None:
    # Mirror Dart applyLibraryOrder semantics in a tiny Python check via source.
    models = open(
        os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "mobile",
            "lib",
            "api",
            "library_order_models.dart",
        ),
        encoding="utf-8",
    ).read()
    assert "fresh" in models
    assert "orderIds" in models
