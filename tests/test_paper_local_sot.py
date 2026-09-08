# -*- coding: utf-8 -*-
"""design/185 — local SoT status flags."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from sentence_reading.api.app import app
from sentence_reading.llm import paper_local_sot as pls


def test_phase_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ASR_PAPER_LOCAL_SOT", raising=False)
    monkeypatch.delenv("ASR_PAPER_LOCAL_SOT_PHASE", raising=False)
    assert pls.paper_local_sot_enabled() is True
    assert pls.paper_local_sot_phase() == 4
    assert pls.paper_disk_store_advertised() is True
    assert pls.paper_handoff_advertised() is True


def test_kill_full_sot(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ASR_PAPER_LOCAL_SOT", "0")
    assert pls.paper_local_sot_enabled() is False
    monkeypatch.setenv("ASR_PAPER_LOCAL_SOT", "1")
    assert pls.paper_local_sot_enabled() is True


def test_status_advertises_phase4() -> None:
    st = TestClient(app).get("/api/status").json()
    assert st["version"] == "0.3.179"
    assert st.get("paper_local_sot") is True
    assert int(st.get("paper_local_sot_phase") or 0) == 4
    assert st.get("paper_disk_store") is True
    assert st.get("paper_handoff") is True
