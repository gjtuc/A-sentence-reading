# -*- coding: utf-8 -*-
"""design/185 Phase 2–4 — handoff ACK + wipe gates."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from sentence_reading.api.app import app
from sentence_reading.llm import paper_handoff as ph
from sentence_reading.llm import paper_local_sot as pls


def test_defaults_enable_wipe(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ASR_PAPER_LOCAL_SOT", raising=False)
    monkeypatch.delenv("ASR_PAPER_LOCAL_SOT_PHASE", raising=False)
    assert pls.paper_local_sot_enabled() is True
    assert pls.paper_local_sot_phase() == 4
    assert ph.handoff_enabled() is True
    assert ph.wipe_on_ack_enabled() is True


def test_kill_disables_wipe(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ASR_PAPER_LOCAL_SOT", "0")
    monkeypatch.setenv("ASR_PAPER_LOCAL_SOT_PHASE", "4")
    assert pls.paper_local_sot_enabled() is False
    assert ph.wipe_on_ack_enabled() is False
    assert ph.handoff_enabled() is True


def test_safe_rel_refuses_traversal() -> None:
    assert ph._safe_rel("../x") is None
    assert ph._safe_rel("session.json") == "session.json"
    assert ph._safe_rel("figures/a.png") == "figures/a.png"
    assert ph._safe_rel("papers/x") is None


def test_refuse_upload_when_acked(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ASR_PAPER_LOCAL_SOT", "1")
    monkeypatch.setenv("ASR_PAPER_LOCAL_SOT_PHASE", "4")

    def fake_state(cid: str):
        return {"acked": True, "wiped": True}

    monkeypatch.setattr(ph, "load_handoff_state", fake_state)
    assert ph.refuse_upload_if_acked("abcd1234efgh") == "handoff_acked"


def test_status_flags() -> None:
    st = TestClient(app).get("/api/status").json()
    assert st["version"] == "0.3.179"
    assert st.get("paper_handoff") is True
    assert st.get("paper_local_sot") is True
    assert int(st.get("paper_local_sot_phase") or 0) == 4


def test_ack_mismatch(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ASR_PAPER_LOCAL_SOT", "1")
    monkeypatch.setenv("ASR_PAPER_LOCAL_SOT_PHASE", "4")
    monkeypatch.setattr(
        ph,
        "load_handoff_state",
        lambda cid: {
            "acked": False,
            "artifact_gen": "genA",
            "content_hash": "hashA",
            "file_count": 2,
        },
    )
    out = ph.apply_handoff_ack(
        "abcd1234efgh",
        content_hash="hashB",
        artifact_gen="genA",
        file_count=2,
    )
    assert out["ok"] is False
    assert out["error"] == "content_hash_mismatch"
