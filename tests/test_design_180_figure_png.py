# -*- coding: utf-8 -*-
"""design/180 — per-figure PNG GET + floor pin."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("ASR_SKIP_ENV_FILE", "1")

from sentence_reading.api.app import app
from sentence_reading.llm.evidence_floor import EVIDENCE_FLOOR_VERSION

ROOT = Path(__file__).resolve().parents[1]
DESIGN = ROOT / "docs" / "design" / "180-figure-hydrate-reliability.md"


def test_design_180_exists() -> None:
    assert DESIGN.is_file()
    text = DESIGN.read_text(encoding="utf-8")
    assert "0.3.163" in text
    assert "figure_png_req" in text
    assert "per-figure PNG" in text or "per-figure PNG GET" in text


def test_status_version_pin_180() -> None:
    st = TestClient(app).get("/api/status").json()
    assert st["version"] == "0.3.163"
    assert EVIDENCE_FLOOR_VERSION == "0.3.163"


def test_cache_figure_png_200_and_404(monkeypatch: pytest.MonkeyPatch) -> None:
    png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16

    def _bytes(cid: str, fid: str):
        if cid == "abcd1234abcd" and fid == "fig-1":
            return png, "ok"
        return None, "missing"

    monkeypatch.setattr(
        "sentence_reading.cache.paper_cache.figure_png_bytes_with_reason",
        _bytes,
    )
    client = TestClient(app)
    ok = client.get("/api/cache/papers/abcd1234abcd/figures/fig-1.png")
    assert ok.status_code == 200
    assert ok.headers.get("content-type", "").startswith("image/png")
    assert ok.content == png
    miss = client.get("/api/cache/papers/abcd1234abcd/figures/nope.png")
    assert miss.status_code == 404
    body = miss.json()
    assert body.get("ok") is False
    assert body.get("error") == "figure_missing"


def test_figure_png_bytes_helper_roundtrip(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from sentence_reading.cache import paper_cache as pc

    monkeypatch.setattr(
        pc,
        "figure_data_url_with_reason",
        lambda _c, _f: ("data:image/png;base64,aGVsbG8=", "ok"),
    )
    raw, reason = pc.figure_png_bytes_with_reason("abcd1234abcd", "fig-1")
    assert reason == "ok"
    assert raw == b"hello"
