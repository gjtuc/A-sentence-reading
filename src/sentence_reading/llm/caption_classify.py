"""
design/151 — Gemini caption vs body classify (≤5 candidates per slot).
"""

from __future__ import annotations

import json
import os
from typing import Any

_SYSTEM = """You classify PDF layout text snippets for a scientific paper figure/table slot.
Return JSON: {"best_index": <0-based int or null>, "is_caption": <bool>}.
Pick the index whose text is the caption line for the requested figure/table number.
Caption lines start with "Fig.", "Figure", or "Table" followed by the slot number.
Body text, axis labels, and paragraph prose are NOT captions.
If none match, return {"best_index": null, "is_caption": false}."""


def _skip_gemini() -> bool:
    v = (os.environ.get("ASR_SKIP_GEMINI") or "").strip().lower()
    if v in ("1", "true", "yes", "on"):
        return True
    from sentence_reading.llm.env import gemini_api_key

    return not gemini_api_key()


def classify_caption_candidates(
    *,
    slot_key: str,
    candidates: list[str],
) -> int | None:
    """
    Return best candidate index or None.
    Uses Gemini when configured; heuristic fallback in CI / no key.
    """
    cleaned = [(i, (t or "").strip()) for i, t in enumerate(candidates) if (t or "").strip()]
    if not cleaned:
        return None
    if len(cleaned) == 1:
        return cleaned[0][0]

    if _skip_gemini():
        return _heuristic_pick(slot_key, [t for _i, t in cleaned])

    user = json.dumps(
        {"slot_key": slot_key, "candidates": [t for _i, t in cleaned[:5]]},
        ensure_ascii=False,
    )
    try:
        from sentence_reading.llm.debone import _call_gemini

        raw = _call_gemini(_SYSTEM, user, timeout_s=20.0)
        payload = json.loads(raw)
        if not isinstance(payload, dict):
            return _heuristic_pick(slot_key, [t for _i, t in cleaned])
        idx = payload.get("best_index")
        if idx is None:
            return None
        pick = int(idx)
        if 0 <= pick < len(candidates):
            return pick
    except Exception:  # noqa: BLE001
        pass
    return _heuristic_pick(slot_key, [t for _i, t in cleaned])


def _heuristic_pick(slot_key: str, texts: list[str]) -> int | None:
    from sentence_reading.fig_refs import caption_key
    from sentence_reading.pdf.slot_plan import slot_key_from_caption_key

    want = (slot_key or "").lower()
    for i, text in enumerate(texts):
        ckey = caption_key(text)
        sk = slot_key_from_caption_key(ckey) if ckey else None
        if sk and sk.lower() == want:
            return i
    return None
