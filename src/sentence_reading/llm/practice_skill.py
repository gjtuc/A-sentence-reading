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


def sample_row_enabled() -> bool:
    """design/364 - whether the phone shows the calibration sample row.

    Missing env means hidden. The row is a tool for measuring a scoring change,
    not a feature anyone reads with, and it cannot be deleted from the library,
    so leaving it on would put a row nobody wants in front of every paper.
    ASR_SAMPLE_ROW=1 brings it back for as long as a calibration round needs it.
    """
    return _env_bool("ASR_SAMPLE_ROW", False)
