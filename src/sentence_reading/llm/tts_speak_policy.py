"""
design/205 — SpeakPolicy for TTS spoken-form (display text ≠ ear text).
"""

from __future__ import annotations

import os
from dataclasses import dataclass


# Bump when spoken rules change in a way that must bust GCS/local MP3 cache.
SPEAK_NORM_VERSION_DEFAULT = "v3"


@dataclass(frozen=True)
class SpeakPolicy:
    """Locked product choices for build_spoken / spoken_text_for_tts."""

    speak_norm_version: str = SPEAK_NORM_VERSION_DEFAULT
    chem_style: str = "symbol_digits"  # later: common_name | letter_spell
    acronym_mode: str = "lexicon"
    full_name_abbrev: str = "prefer_one"
    pause_mode: str = "punctuation"  # later: light_ssml
    locale: str = "en-US"


def load_speak_policy() -> SpeakPolicy:
    """Env override for cache namespace only (rollback / A-B)."""
    ver = (os.environ.get("ASR_TTS_SPEAK_NORM") or SPEAK_NORM_VERSION_DEFAULT).strip()
    if not ver:
        ver = SPEAK_NORM_VERSION_DEFAULT
    return SpeakPolicy(speak_norm_version=ver)


def speak_norm_version() -> str:
    return load_speak_policy().speak_norm_version
