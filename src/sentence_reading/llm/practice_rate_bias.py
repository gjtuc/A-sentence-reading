"""design/267 — practice density→rate bias kill switch.

Default **on**. Operators set ASR_PRACTICE_RATE_BIAS=0 to disable without
killing skill adapt or shadowing practice.
"""

from __future__ import annotations

import os

from sentence_reading.llm.env import load_asr_env


def practice_rate_bias_enabled() -> bool:
    """Unset/1 → on; 0/false/off/no → off."""
    load_asr_env()
    v = (os.environ.get("ASR_PRACTICE_RATE_BIAS") or "1").strip().lower()
    return v not in ("0", "false", "no", "off")
