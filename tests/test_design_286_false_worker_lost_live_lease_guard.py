"""design/286 — false worker_lost live-lease guard + overkill sensors."""
from __future__ import annotations

from pathlib import Path

from sentence_reading.llm.track_verdict import JobTimeline, compute_verdicts

ROOT = Path(__file__).resolve().parents[1]
DESIGN = ROOT / "docs/design/286-false-worker-lost-live-lease-guard.md"
KINDS_PY = ROOT / "src/sentence_reading/llm/evidence_kinds.py"
KINDS_DART = ROOT / "mobile/lib/services/evidence_kinds.dart"
FLOOR = ROOT / "src/sentence_reading/llm/evidence_floor.py"
LEASE = ROOT / "src/sentence_reading/llm/ingest_lease_obs.py"
APP = ROOT / "src/sentence_reading/api/app.py"
WORKER = ROOT / "src/sentence_reading/worker/app.py"
WAKE = ROOT / "src/sentence_reading/llm/ingest_worker_wake.py"
VERDICT = ROOT / "src/sentence_reading/llm/track_verdict.py"
README = ROOT / "docs/design/README.md"
PUBSPEC = ROOT / "mobile/pubspec.yaml"
CONFIG = ROOT / "mobile/lib/config.dart"

VERSION = "0.3.282"
KINDS = (
    "false_worker_lost_guard",
    "false_worker_lost_suspect",
    "post_terminal_ingest_progress",
)


def test_design_286_locked() -> None:
    text = DESIGN.read_text(encoding="utf-8")
    assert "Status: **locked" in text
    assert VERSION in text
    for k in KINDS:
        assert k in text
    assert "skipped_live_gcs_lease" in text
    assert "false_worker_lost_live_gcs" in text


def test_versions_286() -> None:
    assert VERSION in APP.read_text(encoding="utf-8")
    assert VERSION in PUBSPEC.read_text(encoding="utf-8")
    assert VERSION in CONFIG.read_text(encoding="utf-8")
    assert "286-false-worker-lost-live-lease-guard.md" in README.read_text(
        encoding="utf-8"
    )


def test_kinds_mirrored_286() -> None:
    from sentence_reading.llm.evidence_floor import FROZEN_KINDS
    from sentence_reading.llm.evidence_kinds import ALLOWED_KINDS
    from sentence_reading.llm.ops_events import _ALLOWED_KINDS as OPS

    py = KINDS_PY.read_text(encoding="utf-8")
    dart = KINDS_DART.read_text(encoding="utf-8")
    for k in KINDS:
        assert k in ALLOWED_KINDS
        assert k in FROZEN_KINDS
        assert k in OPS
        assert f'"{k}"' in py or f"'{k}'" in py
        assert f"'{k}'" in dart


def test_emit_markers_286() -> None:
    app = APP.read_text(encoding="utf-8")
    lease = LEASE.read_text(encoding="utf-8")
    floor = FLOOR.read_text(encoding="utf-8")
    assert "false_worker_lost_guard" in app
    assert "skipped_live_gcs_lease" in app
    assert "post_terminal_ingest_progress" in app
    assert "kill_skip_for_live_lease" in lease
    assert "kill_skip_for_live_lease" in floor
    assert "wake_error" in WAKE.read_text(encoding="utf-8")
    assert '"error"' in WORKER.read_text(encoding="utf-8") or "error=" in WORKER.read_text(
        encoding="utf-8"
    )
    assert "false_worker_lost_live_gcs" in VERDICT.read_text(encoding="utf-8")


def test_kill_skip_live_gcs_after_wake_fail() -> None:
    from sentence_reading.llm import ingest_lease_obs as ilo

    skip = ilo.kill_skip_for_live_lease(
        reclaim_ok=False,
        reclaim_reason="worker_wake_failed",
        mem_snap={"mem_lease_age_sec": -274, "mem_tok8": "ta424db75"},
        gcs_snap={
            "gcs_lease_missing": False,
            "gcs_lease_age_sec": -274,
            "gcs_tok8": "ta424db75",
        },
    )
    assert skip == "skipped_live_gcs_lease"


def test_kill_allowed_when_lease_expired() -> None:
    from sentence_reading.llm import ingest_lease_obs as ilo

    skip = ilo.kill_skip_for_live_lease(
        reclaim_ok=False,
        reclaim_reason="worker_wake_failed",
        mem_snap={"mem_lease_age_sec": 40},
        gcs_snap={"gcs_lease_missing": False, "gcs_lease_age_sec": 40},
    )
    assert skip is None


def test_track_verdict_live_gcs_false_lost() -> None:
    events = [
        {
            "kind": "server_job_terminal_error",
            "ts": "2026-09-15T11:14:23Z",
            "details": {
                "reason_enum": "worker_lost",
                "reclaim_reason": "worker_wake_failed",
                "mem_lease_age_sec": -274,
                "gcs_lease_age_sec": -274,
            },
            "ok": False,
        },
        {
            "kind": "progress_view",
            "ts": "2026-09-15T11:14:28Z",
            "details": {},
            "ok": True,
        },
    ]
    tl = JobTimeline.from_events(events)
    verdicts = compute_verdicts(tl, ui_pct=None, open_hangs=[], silence_s=10, prev={})
    assert "worker_lost_terminal" in verdicts
    assert "false_worker_lost_live_gcs" in verdicts
    assert "false_worker_lost_wake_fail_live" in verdicts
