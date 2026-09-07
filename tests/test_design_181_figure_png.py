# -*- coding: utf-8 -*-
"""design/181 — PNG self-contained session ensure + raw bytes."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("ASR_SKIP_ENV_FILE", "1")

from sentence_reading.api.app import app
from sentence_reading.cache import paper_cache as pc
from sentence_reading.llm.evidence_floor import EVIDENCE_FLOOR_VERSION

ROOT = Path(__file__).resolve().parents[1]
DESIGN = ROOT / "docs" / "design" / "181-figure-png-self-contained.md"


def test_design_181_exists() -> None:
    assert DESIGN.is_file()
    text = DESIGN.read_text(encoding="utf-8")
    assert "0.3.165" in text
    assert "session_ensured" in text
    assert "self-contained" in text.lower() or "self-contained" in text


def test_status_version_pin_181() -> None:
    st = TestClient(app).get("/api/status").json()
    assert st["version"] == "0.3.165"
    assert EVIDENCE_FLOOR_VERSION == "0.3.165"


def test_png_cold_session_ensure_then_200(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cid = "abcd1234abcd"
    fid = "fig-1"
    png = b"\x89PNG\r\n\x1a\n" + b"raw-png-bytes"
    root = tmp_path / cid
    fig = root / "figures" / "a.png"

    def _refresh(cache_id: str):
        assert cache_id == cid
        fig.parent.mkdir(parents=True, exist_ok=True)
        fig.write_bytes(png)
        meta = {
            "figures": [{"id": fid, "file": "figures/a.png"}],
            "title": "T",
        }
        (root / "session.json").write_text(json.dumps(meta), encoding="utf-8")
        return True, "ok"

    monkeypatch.setattr(pc, "cache_root", lambda: tmp_path)
    monkeypatch.setattr(pc, "_session_ensure_at", {})
    monkeypatch.setattr(
        "sentence_reading.llm.papers_gcs.gcs_papers_ready", lambda: True
    )
    monkeypatch.setattr(
        "sentence_reading.llm.papers_gcs.refresh_paper_for_open", _refresh
    )

    raw, reason, details = pc.figure_png_lookup(cid, fid)
    assert reason == "ok"
    assert raw == png
    assert details["session_ensured"] == 1
    # second call within TTL should not re-ensure
    raw2, reason2, details2 = pc.figure_png_lookup(cid, fid)
    assert reason2 == "ok" and raw2 == png
    assert details2["session_ensured"] == 0


def test_png_gcs_pull_fail_no_leftover(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cid = "abcd1234abcd"
    # leftover from another tenant on disk
    root = tmp_path / cid
    root.mkdir(parents=True)
    (root / "session.json").write_text(
        json.dumps({"figures": [{"id": "fig-1", "file": "figures/a.png"}]}),
        encoding="utf-8",
    )
    (root / "figures").mkdir()
    (root / "figures" / "a.png").write_bytes(b"LEFTOVER")

    monkeypatch.setattr(pc, "cache_root", lambda: tmp_path)
    monkeypatch.setattr(pc, "_session_ensure_at", {})
    monkeypatch.setattr(
        "sentence_reading.llm.papers_gcs.gcs_papers_ready", lambda: True
    )
    monkeypatch.setattr(
        "sentence_reading.llm.papers_gcs.refresh_paper_for_open",
        lambda _cid: (False, "gcs_pull_failed"),
    )
    raw, reason, _ = pc.figure_png_lookup(cid, "fig-1")
    assert raw is None
    assert reason == "gcs_pull_failed"


def test_png_lookup_does_not_use_data_url_roundtrip(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cid = "abcd1234abcd"
    fid = "fig-1"
    png = b"\x89PNG\r\n\x1a\ndirect"
    root = tmp_path / cid
    root.mkdir()
    (root / "figures").mkdir()
    (root / "figures" / "a.png").write_bytes(png)
    (root / "session.json").write_text(
        json.dumps({"figures": [{"id": fid, "file": "figures/a.png"}]}),
        encoding="utf-8",
    )

    def _boom(*_a, **_k):
        raise AssertionError("data-URL path must not be used for PNG lookup")

    monkeypatch.setattr(pc, "cache_root", lambda: tmp_path)
    monkeypatch.setattr(pc, "_session_ensure_at", {cid: 10**12})  # ttl ok
    monkeypatch.setattr(pc, "_figure_to_data_url", _boom)
    monkeypatch.setattr(pc, "figure_data_url_with_reason", _boom)

    raw, reason, _ = pc.figure_png_lookup(cid, fid)
    assert reason == "ok"
    assert raw == png
