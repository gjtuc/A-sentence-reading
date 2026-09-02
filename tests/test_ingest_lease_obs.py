"""design/169m — lease age / snapshot helpers."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sentence_reading.llm import ingest_lease_obs as ilo
from sentence_reading.llm.evidence_bus import _safe_details


def test_lease_age_sec_signs() -> None:
    now = datetime(2026, 9, 2, 12, 0, 0, tzinfo=timezone.utc)
    alive = {"lease_until": (now + timedelta(seconds=200)).isoformat()}
    dead = {"lease_until": (now - timedelta(seconds=40)).isoformat()}
    assert ilo.lease_age_sec(alive, now=now) == -200
    assert ilo.lease_age_sec(dead, now=now) == 40
    assert ilo.lease_age_sec({}, now=now) is None


def test_safe_details_keeps_lease_fields() -> None:
    raw = {
        "action": "reclaim",
        "reclaim_reason": "gcs_lease_alive",
        "mem_lease_age_sec": 12,
        "gcs_lease_age_sec": -275,
        "local_running": False,
        "cr_rev8": "rabcdef12",
        "mem_tok8": "tabc12345",
        "will_mark_lost": True,
        "lease_ttl_s": 300,
        # dropped by bus:
        "lease_until": "2026-09-02T12:00:00Z",
        "bad Text": "no",
    }
    out = _safe_details(raw)
    assert out["action"] == "reclaim"
    assert out["reclaim_reason"] == "gcs_lease_alive"
    assert out["mem_lease_age_sec"] == 12
    assert out["gcs_lease_age_sec"] == -275
    assert out["local_running"] is False
    assert out["cr_rev8"] == "rabcdef12"
    assert out["mem_tok8"] == "tabc12345"
    assert out["will_mark_lost"] is True
    assert "lease_until" not in out


def test_should_emit_heartbeat_every_fourth() -> None:
    assert ilo.should_emit_heartbeat(4) is True
    assert ilo.should_emit_heartbeat(5) is False
    assert ilo.should_emit_heartbeat(3, force=True) is True


def test_why_sweep_none_local_running() -> None:
    assert ilo.why_sweep_none({"_local_running": True, "done": False}) == "local_running"
