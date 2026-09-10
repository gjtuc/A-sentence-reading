"""design/212 — practice skill adapt kill flags."""

from __future__ import annotations

import os


def _env_bool(name: str, default: bool) -> bool:
    raw = (os.environ.get(name) or "").strip().lower()
    if not raw:
        return default
    if raw in ("0", "false", "off", "no"):
        return False
    if raw in ("1", "true", "on", "yes"):
        return True
    return default


def practice_skill_enabled() -> bool:
    """Missing env → on. ASR_PRACTICE_SKILL=0 kills scoring/adapt/calendar %."""
    return _env_bool("ASR_PRACTICE_SKILL", True)


def practice_stt_cloud_enabled() -> bool:
    """Interim Gemini recognize for takes. Default on with skill; explicit 0 kills."""
    if not practice_skill_enabled():
        return False
    return _env_bool("ASR_PRACTICE_STT_CLOUD", True)
