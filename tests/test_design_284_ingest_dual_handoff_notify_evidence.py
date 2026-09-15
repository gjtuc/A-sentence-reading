"""design/284 — ingest dual/handoff/notify evidence densify."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DESIGN = ROOT / "docs/design/284-ingest-dual-handoff-notify-evidence.md"
KINDS_PY = ROOT / "src/sentence_reading/llm/evidence_kinds.py"
KINDS_DART = ROOT / "mobile/lib/services/evidence_kinds.dart"
FLOOR = ROOT / "src/sentence_reading/llm/evidence_floor.py"
CTRL = ROOT / "mobile/lib/state/library_controller.dart"
GATE = ROOT / "mobile/lib/services/notify_complete_gate_evidence.dart"
PAPERS = ROOT / "src/sentence_reading/llm/papers_gcs.py"
LEASE = ROOT / "src/sentence_reading/llm/ingest_lease_obs.py"
CACHE = ROOT / "src/sentence_reading/cache/paper_cache.py"
HANDOFF = ROOT / "src/sentence_reading/llm/paper_handoff.py"
APP = ROOT / "src/sentence_reading/api/app.py"
PUBSPEC = ROOT / "mobile/pubspec.yaml"
CONFIG = ROOT / "mobile/lib/config.dart"
README = ROOT / "docs/design/README.md"

KINDS = (
    "ingest_lease_dual",
    "ingest_cache_id_fork",
    "notify_complete_gate",
    "poll_cache_vs_index",
)

VERSION = "0.3.279"


def test_design_284_locked() -> None:
    text = DESIGN.read_text(encoding="utf-8")
    assert "Status: **locked" in text
    assert VERSION in text
    for k in KINDS:
        assert k in text
    assert "notify_without_handoff" in text
    assert "`c`" in text or "c{cache_id}" in text


def test_versions_284() -> None:
    # Ship pin lives in the design chip; later chips may bump app/pubspec/config.
    assert VERSION in DESIGN.read_text(encoding="utf-8")
    assert "284-ingest-dual-handoff-notify-evidence.md" in README.read_text(
        encoding="utf-8"
    )
    assert "0.3." in PUBSPEC.read_text(encoding="utf-8")
    assert "0.3." in CONFIG.read_text(encoding="utf-8")
    assert "0.3." in APP.read_text(encoding="utf-8")


def test_kinds_mirrored_284() -> None:
    from sentence_reading.llm.evidence_kinds import ALLOWED_KINDS
    from sentence_reading.llm.evidence_floor import FROZEN_KINDS

    py = KINDS_PY.read_text(encoding="utf-8")
    dart = KINDS_DART.read_text(encoding="utf-8")
    for k in KINDS:
        assert k in ALLOWED_KINDS
        assert f'"{k}"' in py or f"'{k}'" in py
        assert f"'{k}'" in dart
        assert k in FROZEN_KINDS


def test_emit_markers_284() -> None:
    ctrl = CTRL.read_text(encoding="utf-8")
    floor = FLOOR.read_text(encoding="utf-8")
    for k in KINDS:
        assert k in floor
    assert "notify_complete_gate" in ctrl
    assert "_emitNotifyCompleteGate" in ctrl
    assert "_emitPollCacheVsIndex" in ctrl
    assert "miss_reason" in ctrl
    assert "handoff_ok" in ctrl
    assert "fail_code" in ctrl
    assert "maybe_emit_lease_dual" in LEASE.read_text(encoding="utf-8")
    assert "ingest_lease_dual" in APP.read_text(encoding="utf-8") or (
        "maybe_emit_lease_dual" in APP.read_text(encoding="utf-8")
    )
    assert "_maybe_emit_cache_id_fork" in CACHE.read_text(encoding="utf-8")
    assert "ingest_cache_id_fork" in CACHE.read_text(encoding="utf-8")
    papers = PAPERS.read_text(encoding="utf-8")
    assert "detail_cache_id" in papers
    assert "join_incomplete" in papers
    assert "handoff_ok" in HANDOFF.read_text(encoding="utf-8")
    assert "fail_code" in HANDOFF.read_text(encoding="utf-8")
    assert GATE.is_file()
    gate = GATE.read_text(encoding="utf-8")
    assert "buildNotifyCompleteGateDetails" in gate
    assert "notify_without_handoff" in gate


def test_safe_details_winner_id_prefix() -> None:
    from sentence_reading.llm.evidence_bus import _safe_details, detail_cache_id

    raw = "18ed9907bba5"
    assert detail_cache_id(raw) == "c18ed9907bba5"
    dropped = _safe_details({"winner_id": raw})
    assert "winner_id" not in dropped
    kept = _safe_details({"winner_id": detail_cache_id(raw), "deleted_n": 18})
    assert kept.get("winner_id") == "c18ed9907bba5"
    assert kept.get("deleted_n") == 18


def test_maybe_emit_lease_dual_helper_exists() -> None:
    from sentence_reading.llm import ingest_lease_obs as ilo

    assert callable(ilo.maybe_emit_lease_dual)
