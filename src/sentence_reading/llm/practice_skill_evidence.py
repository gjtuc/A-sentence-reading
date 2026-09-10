"""design/213 — practice skill dense evidence kill."""

from __future__ import annotations

import os

from sentence_reading.llm.practice_skill import practice_skill_enabled


def _env_bool(name: str, default: bool) -> bool:
    raw = (os.environ.get(name) or "").strip().lower()
    if not raw:
        return default
    if raw in ("0", "false", "off", "no"):
        return False
    if raw in ("1", "true", "on", "yes"):
        return True
    return default


def practice_skill_evidence_enabled() -> bool:
    """Missing → on (first-use observation). Requires skill feature on."""
    if not practice_skill_enabled():
        return False
    return _env_bool("ASR_PRACTICE_SKILL_EVIDENCE", True)
