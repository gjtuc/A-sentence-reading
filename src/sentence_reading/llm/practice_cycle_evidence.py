"""design/209 — practice cycle wide evidence kill switch.

Default **on**. ASR_PRACTICE_CYCLE_EVIDENCE=0 disables collection/upload
without killing shadowing practice or process grooming.
"""

from __future__ import annotations

import os

from sentence_reading.llm.env import load_asr_env


def practice_cycle_evidence_enabled() -> bool:
    """Unset/1 → on; 0/false/off/no → off."""
    load_asr_env()
    v = (os.environ.get("ASR_PRACTICE_CYCLE_EVIDENCE") or "1").strip().lower()
    return v not in ("0", "false", "no", "off")
