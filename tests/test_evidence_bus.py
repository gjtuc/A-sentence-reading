# -*- coding: utf-8 -*-
"""design/169a — evidence_bus + POST /api/evidence/ingest (no GET UI)."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("ASR_SKIP_ENV_FILE", "1")

from sentence_reading.api.app import app
from sentence_reading.llm import evidence_bus as eb
from sentence_reading.llm.evidence_kinds import ALLOWED_KINDS

ROOT = Path(__file__).resolve().parents[1]
DESIGN = ROOT / "docs" / "design" / "169-agent-evidence-bus.md"
APP_SRC = (ROOT / "src" / "sentence_reading" / "api" / "app.py").read_text(
    encoding="utf-8"
)


@pytest.fixture()
def ev_tmp(tmp_path, monkeypatch):
    monkeypatch.setenv("ASR_EVIDENCE_BUS", "1")
    monkeypatch.setattr(eb, "local_events_path", lambda: tmp_path / "evidence.jsonl")
    monkeypatch.setattr(eb, "_gcs_events_object", lambda: None)
    monkeypatch.setattr(eb, "_RATE_MEM", {})
    return tmp_path


def test_design_doc_exists() -> None:
    assert DESIGN.is_file()
    text = DESIGN.read_text(encoding="utf-8")
    assert "evidence_bus" in text or "Evidence Bus" in text
    assert "UI 없음" in text or "UI 제로" in text


def test_no_get_evidence_route() -> None:
    assert '@app.get("/api/evidence' not in APP_SRC
    assert "GET /api/evidence" not in APP_SRC


def test_allowlist_drop(ev_tmp) -> None:
    assert "client_api_fail" in ALLOWED_KINDS
    assert eb.build_event("not_a_real_kind") is None
    eb.emit("not_a_real_kind", message="x")
    assert not eb.local_events_path().is_file()


def test_kill_switch(ev_tmp, monkeypatch) -> None:
    monkeypatch.setenv("ASR_EVIDENCE_BUS", "0")
    assert eb.evidence_bus_enabled() is False
    eb.emit("stall_fired", message="x")
    assert not eb.local_events_path().is_file()


def test_emit_round_trip(ev_tmp) -> None:
    eb.emit(
        "figure_preserve_miss",
        owner_uid="user123",
        cache_id="abcd1234ef99",
        details={"prior_png": 0, "session_figs": 7, "forced": 1},
        severity="consistency",
    )
    rows = eb.list_events(limit=5)
    assert len(rows) == 1
    assert rows[0]["kind"] == "figure_preserve_miss"
    assert rows[0]["details"]["prior_png"] == 0


def test_body_uid_ignored(ev_tmp, monkeypatch) -> None:
    accepted, dropped = eb.ingest_client_batch(
        [
            {
                "kind": "client_api_fail",
                "source": "mobile",
                "severity": "error",
                "message": "처리에 실패했습니다.",
                "owner_uid": "attacker",
                "uid": "attacker",
                "details": {"want_translate_pref": True},
            }
        ],
        owner_uid="real_user_1",
    )
    assert accepted == 1
    assert dropped == 0
    row = eb.list_events(limit=1)[0]
    assert row["owner_uid"] == "real_user_1"
    assert row["details"]["want_translate_pref"] is True


def test_status_evidence_bus_pin(ev_tmp) -> None:
    st = TestClient(app).get("/api/status").json()
    assert st["version"] == "0.3.123"
    assert st.get("evidence_bus") is True


def test_status_evidence_bus_kill(monkeypatch) -> None:
    monkeypatch.setenv("ASR_EVIDENCE_BUS", "0")
    st = TestClient(app).get("/api/status").json()
    assert st.get("evidence_bus") is False


def test_ingest_endpoint_requires_auth(ev_tmp) -> None:
    res = TestClient(app).post(
        "/api/evidence/ingest",
        json={"events": [{"kind": "client_api_fail", "message": "x"}]},
    )
    assert res.status_code == 401


def test_pull_script_help() -> None:
    import subprocess
    import sys

    script = ROOT / "scripts" / "pull_evidence.py"
    assert script.is_file()
    proc = subprocess.run(
        [sys.executable, str(script), "--help"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0
    assert "evidence" in (proc.stdout + proc.stderr).lower()
