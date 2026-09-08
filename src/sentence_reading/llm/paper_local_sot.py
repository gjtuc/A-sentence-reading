"""design/185 — local paper SoT flags (Phase 1–4)."""

from __future__ import annotations

import os


def paper_local_sot_enabled() -> bool:
    """Handoff ACK → cloud papers wipe. Default on for 0.3.179+ cutover."""
    v = (os.environ.get("ASR_PAPER_LOCAL_SOT") or "1").strip().lower()
    return v not in ("0", "false", "off", "no")


def paper_local_sot_phase() -> int:
    """2+ = handoff APIs; wipe still requires paper_local_sot_enabled()."""
    raw = (os.environ.get("ASR_PAPER_LOCAL_SOT_PHASE") or "4").strip()
    try:
        n = int(raw)
    except ValueError:
        return 4
    return max(0, min(n, 7))


def paper_disk_store_advertised() -> bool:
    return paper_local_sot_phase() >= 1


def paper_handoff_advertised() -> bool:
    return paper_local_sot_phase() >= 2


def status_fields() -> dict:
    return {
        "paper_local_sot": paper_local_sot_enabled(),
        "paper_local_sot_phase": paper_local_sot_phase(),
        "paper_disk_store": paper_disk_store_advertised(),
        "paper_handoff": paper_handoff_advertised(),
    }
