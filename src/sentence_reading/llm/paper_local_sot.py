"""design/185 — local paper SoT flags (Phase 1 store; wipe later)."""

from __future__ import annotations

import os


def paper_local_sot_enabled() -> bool:
    """Full local-SoT cutover (handoff wipe). Default off until Phase 4."""
    v = (os.environ.get("ASR_PAPER_LOCAL_SOT") or "0").strip().lower()
    return v in ("1", "true", "on", "yes")


def paper_local_sot_phase() -> int:
    """Advertised rollout phase: 1 = device store + shadow persist only."""
    raw = (os.environ.get("ASR_PAPER_LOCAL_SOT_PHASE") or "1").strip()
    try:
        n = int(raw)
    except ValueError:
        return 1
    return max(0, min(n, 7))


def paper_disk_store_advertised() -> bool:
    """Phase 1+: clients may shadow-persist; always advertised when phase >= 1."""
    return paper_local_sot_phase() >= 1


def status_fields() -> dict:
    return {
        "paper_local_sot": paper_local_sot_enabled(),
        "paper_local_sot_phase": paper_local_sot_phase(),
        "paper_disk_store": paper_disk_store_advertised(),
    }
