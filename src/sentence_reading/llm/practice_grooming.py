"""design/208 — practice process grooming kill switch.

Default **on**. Operators set ASR_PRACTICE_GROOMING=0 to disable without
killing the shadowing practice loop.
"""

from __future__ import annotations

import os

from sentence_reading.llm.env import load_asr_env


def practice_grooming_enabled() -> bool:
    """Unset/1 → on; 0/false/off/no → off."""
    load_asr_env()
    v = (os.environ.get("ASR_PRACTICE_GROOMING") or "1").strip().lower()
    return v not in ("0", "false", "no", "off")
