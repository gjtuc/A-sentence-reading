# -*- coding: utf-8 -*-
"""design/185 leftovers — abandon TTL."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from sentence_reading.api.app import app
from sentence_reading.llm import paper_handoff as ph


def test_should_abandon_pending_aged() -> None:
    now = datetime(2026, 9, 8, tzinfo=timezone.utc)
    st = {
        "acked": False,
        "pending": True,
        "manifest_built_at": (now - timedelta(hours=80)).isoformat(),
    }
    ok, reason = ph.should_abandon_handoff(st, now=now)
    assert ok is True
    assert reason == "abandon_ttl"


def test_should_keep_pending_fresh() -> None:
    now = datetime(2026, 9, 8, tzinfo=timezone.utc)
    st = {
        "acked": False,
        "pending": True,
        "manifest_built_at": (now - timedelta(hours=10)).isoformat(),
    }
    ok, reason = ph.should_abandon_handoff(st, now=now)
    assert ok is False
    assert reason == "not_yet"


def test_should_not_abandon_acked() -> None:
    now = datetime(2026, 9, 8, tzinfo=timezone.utc)
    st = {
        "acked": True,
        "pending": False,
        "manifest_built_at": (now - timedelta(hours=200)).isoformat(),
    }
    ok, reason = ph.should_abandon_handoff(st, now=now)
    assert ok is False
    assert reason == "acked"


def test_abandon_kill(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ASR_PAPER_HANDOFF_ABANDON_TTL", "0")
    assert ph.abandon_ttl_enabled() is False


def test_refuse_abandoned_wiped(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ASR_PAPER_LOCAL_SOT", "1")
    monkeypatch.setenv("ASR_PAPER_LOCAL_SOT_PHASE", "4")
    monkeypatch.setattr(
        ph,
        "load_handoff_state",
        lambda cid: {"abandoned": True, "wiped": True, "acked": False},
    )
    assert ph.refuse_upload_if_acked("abcd1234efgh") == "handoff_abandoned"


def test_status_abandon_flags() -> None:
    st = TestClient(app).get("/api/status").json()
    assert st["version"] == "0.3.181"
    assert st.get("paper_handoff_abandon_ttl") is True
    assert int(st.get("paper_handoff_abandon_hours") or 0) == 72
