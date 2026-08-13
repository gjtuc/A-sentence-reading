# -*- coding: utf-8 -*-
"""design/122 — library reorder drag without white flash."""
from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from sentence_reading.api.app import app

ROOT = Path(__file__).resolve().parents[1]
DESIGN = ROOT / "docs" / "design" / "122-library-reorder-no-white-flash.md"
PROXY = ROOT / "mobile" / "lib" / "api" / "library_reorder_proxy.dart"
SCREEN = ROOT / "mobile" / "lib" / "screens" / "library_screen.dart"
PUB = ROOT / "mobile" / "pubspec.yaml"


def test_design_and_wiring() -> None:
    assert DESIGN.is_file()
    text = DESIGN.read_text(encoding="utf-8")
    # Chip 122 shipped at 0.3.36; later chips bump pub/status only.
    assert "0.3.36" in text
    assert "proxyDecorator" in text or "proxy" in text.lower()
    proxy = PROXY.read_text(encoding="utf-8")
    assert "libraryReorderProxyDecorator" in proxy
    assert "surfaceTintColor" in proxy
    assert "Colors.transparent" in proxy
    src = SCREEN.read_text(encoding="utf-8")
    assert "design/122" in src
    assert "proxyDecorator" in src
    assert "libraryReorderProxyDecorator" in src
    # Product 4A — reorderPapers still used; no rewrite of save path in this chip.
    assert "reorderPapers" in src
    assert "0.3.44" in PUB.read_text(encoding="utf-8")
    st = TestClient(app).get("/api/status").json()
    assert st["version"] == "0.3.44"
