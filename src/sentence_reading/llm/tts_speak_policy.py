"""
design/205 — SpeakPolicy for TTS spoken-form (display text ≠ ear text).
"""

from __future__ import annotations

import os
from dataclasses import dataclass


# Bump when spoken rules change in a way that must bust GCS/local MP3 cache.
# v7 — design/326: token-typed decisions, acronyms atomic, compound names never
# composed from parts, abbreviation definitions voiced.
# v8 — design/339: subscript words read as words, italics mark a variable,
# supplementary labels are not sulfur, dotted abbreviations expanded before freeze,
# a lone capital is not an element, angle brackets are comparisons, prose slash,
# molar/time units, Greek letters in subscripts. Cached MP3s carry the old wording,
# so the namespace has to change with the rules.
# v9 — design/341: unit runs read as grammar, restoring a positive exponent the
# citation rule had been deleting, and a slash between symbols read as a ratio.
SPEAK_NORM_VERSION_DEFAULT = "v9"


@dataclass(frozen=True)
class SpeakPolicy:
    """Locked product choices for build_spoken / spoken_text_for_tts."""

    speak_norm_version: str = SPEAK_NORM_VERSION_DEFAULT
    chem_style: str = "symbol_digits"  # later: common_name | letter_spell
    acronym_mode: str = "lexicon"
    # design/326 — say the long form and the abbreviation. `prefer_one` dropped
    # the abbreviation at its definition and then read bare letters in later
    # sentences, so the listener never heard the term defined.
    full_name_abbrev: str = "say_both"
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
