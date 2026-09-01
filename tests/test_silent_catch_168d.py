# -*- coding: utf-8 -*-
"""design/168d — silent catch → ops events / reasons (report-only)."""

from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("ASR_SKIP_ENV_FILE", "1")

from sentence_reading.api import app as app_mod
from sentence_reading.api.app import app
from sentence_reading.cache import paper_cache as pc
from sentence_reading.llm import ops_events as oev
from sentence_reading.llm import papers_gcs as pg


@pytest.fixture()
def ops_tmp(tmp_path, monkeypatch):
    monkeypatch.setenv("ASR_OPS_EVENTS", "1")
    monkeypatch.setattr(oev, "local_events_path", lambda: tmp_path / "ops_events.jsonl")
    monkeypatch.setattr(oev, "_gcs_events_object", lambda: None)
    return tmp_path


def test_status_silent_catch_report_pin(ops_tmp) -> None:
    st = TestClient(app).get("/api/status").json()
    assert st["version"] == "0.3.120"
    assert st.get("silent_catch_report") is True


def test_168d_kinds_allowlisted(ops_tmp) -> None:
    for kind in (
        "figure_window_empty",
        "figure_data_url_miss",
        "figure_blob_miss",
        "open_translate_backfill_fail",
    ):
        oev.emit(kind, cache_id="abcd1234", details={"reason": "bad_cache_id"})
    kinds = {r["kind"] for r in oev.list_events(limit=20)}
    assert kinds == {
        "figure_window_empty",
        "figure_data_url_miss",
        "figure_blob_miss",
        "open_translate_backfill_fail",
    }


def test_figure_data_url_miss_reason_and_event(ops_tmp) -> None:
    url, reason = pc.figure_data_url_with_reason("../etc", "fig-1")
    assert url is None
    assert reason == "bad_cache_id"
    assert pc.figure_data_url("../etc", "fig-1") is None
    rows = [r for r in oev.list_events(limit=10) if r["kind"] == "figure_data_url_miss"]
    assert rows
    assert rows[-1]["details"]["reason"] == "bad_cache_id"


def test_ensure_figure_local_miss_reason_and_event(ops_tmp) -> None:
    path, reason = pg.ensure_figure_local_with_reason("bad id!", "figures/x.png")
    assert path is None
    assert reason == "bad_cache_id"
    assert pg.ensure_figure_local("bad id!", "figures/x.png") is None
    rows = [r for r in oev.list_events(limit=10) if r["kind"] == "figure_blob_miss"]
    assert rows
    assert rows[-1]["details"]["reason"] == "bad_cache_id"


def test_figure_window_empty_event(ops_tmp, monkeypatch) -> None:
    fig = SimpleNamespace(
        id="fig-1",
        image_src="",
        caption="c",
        caption_ko="",
        caption_ko_stage="",
    )
    session = SimpleNamespace(figures=[fig])
    monkeypatch.setitem(app_mod._SESSIONS, "ses_aabbccddeeff", session)
    # No _SESSION_CACHE_IDS → skip figure_data_url; empty src stays empty.

    res = TestClient(app).get(
        "/api/session/ses_aabbccddeeff/figures/window",
        params={"center": 0, "span": 1},
    )
    assert res.status_code == 200
    body = res.json()
    assert body.get("ok") is True
    assert body.get("figures")
    assert all(not (f.get("image_src") or "").strip() for f in body["figures"])
    kinds = [r["kind"] for r in oev.list_events(limit=20)]
    assert "figure_window_empty" in kinds
