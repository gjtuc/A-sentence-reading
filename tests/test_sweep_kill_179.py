"""design/179 — false worker_lost skip predicates + sweep_kill_decision emit."""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("ASR_SKIP_ENV_FILE", "1")

_ZOMBIE = frozenset({"gcs_lease_alive", "lease_claim_failed", "already_local"})


def _will_mark_lost(
    *,
    ok: bool,
    local_running: bool,
    done: bool,
    error: object,
    reclaim_reason: str,
) -> bool:
    return (
        not ok
        and not local_running
        and not done
        and not error
        and reclaim_reason not in _ZOMBIE
    )


def test_zombie_gcs_lease_alive_never_marks_lost() -> None:
    assert (
        _will_mark_lost(
            ok=False,
            local_running=False,
            done=False,
            error=None,
            reclaim_reason="gcs_lease_alive",
        )
        is False
    )


def test_true_orphan_wake_failed_still_marks() -> None:
    assert (
        _will_mark_lost(
            ok=False,
            local_running=False,
            done=False,
            error=None,
            reclaim_reason="worker_wake_failed",
        )
        is True
    )


def test_sweep_kill_decision_allowlisted(ev_tmp=None) -> None:
    from sentence_reading.llm.evidence_kinds import ALLOWED_KINDS
    from sentence_reading.llm.ops_events import _ALLOWED_KINDS as OPS

    assert "sweep_kill_decision" in ALLOWED_KINDS
    assert "ingest_poll_terminal" in ALLOWED_KINDS
    assert "sweep_kill_decision" in OPS


def test_emit_sweep_kill_decision(tmp_path, monkeypatch) -> None:
    from sentence_reading.llm import evidence_bus as eb
    from sentence_reading.llm import ingest_lease_obs as ilo

    monkeypatch.setenv("ASR_EVIDENCE_BUS", "1")
    monkeypatch.setattr(eb, "local_events_path", lambda: tmp_path / "evidence.jsonl")
    monkeypatch.setattr(eb, "_gcs_events_object", lambda: None)
    monkeypatch.setattr(eb, "_RATE_MEM", {})

    ilo.emit_dual(
        "sweep_kill_decision",
        job_id="job_deadbeef0001",
        severity="boundary",
        percent=91,
        details={
            "decision": "skipped_zombie",
            "reclaim_reason": "gcs_lease_alive",
            "reclaim_ok": False,
            "zombie_risk": True,
            "will_mark_lost": False,
        },
        ok=True,
        owner_uid="uid123456789012345678",
    )
    rows = [r for r in eb.list_events(limit=10) if r["kind"] == "sweep_kill_decision"]
    assert rows
    assert rows[0]["details"]["decision"] == "skipped_zombie"
    assert rows[0]["details"]["zombie_risk"] is True
