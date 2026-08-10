"""design/79 — shadowing practice series kill switch (opt-in foundation).

Default **off** so Cloud Run does not advertise the preference UI until
operators set ASR_SHADOWING_PRACTICE=1. Practice loop itself is Later chips.
"""

from __future__ import annotations

import os

from sentence_reading.llm.env import load_asr_env


def shadowing_practice_enabled() -> bool:
    """ASR_SHADOWING_PRACTICE=1 → on; unset/0/false → off (fail-closed)."""
    load_asr_env()
    v = (os.environ.get("ASR_SHADOWING_PRACTICE") or "0").strip().lower()
    return v in ("1", "true", "yes", "on")
