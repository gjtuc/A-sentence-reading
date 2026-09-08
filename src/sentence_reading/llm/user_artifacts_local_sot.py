"""design/187 — user artifacts device SoT flags (bookmarks/annotations/shadowing/notes)."""

from __future__ import annotations

import os


def _env_on(name: str, default: str = "1") -> bool:
    v = (os.environ.get(name) or default).strip().lower()
    return v not in ("0", "false", "off", "no")


def bookmarks_local_sot_enabled() -> bool:
    return _env_on("ASR_BOOKMARKS_LOCAL_SOT", "1")


def annotations_local_sot_enabled() -> bool:
    return _env_on("ASR_ANNOTATIONS_LOCAL_SOT", "1")


def shadowing_local_sot_enabled() -> bool:
    return _env_on("ASR_SHADOWING_LOCAL_SOT", "1")


def notes_local_sot_enabled() -> bool:
    return _env_on("ASR_NOTES_LOCAL_SOT", "1")


def status_fields() -> dict:
    return {
        "bookmarks_local_sot": bookmarks_local_sot_enabled(),
        "annotations_local_sot": annotations_local_sot_enabled(),
        "shadowing_local_sot": shadowing_local_sot_enabled(),
        "notes_local_sot": notes_local_sot_enabled(),
    }
