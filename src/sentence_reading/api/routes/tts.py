"""design/255 Phase 1 — TTS domain router (voices / synthesize / spoken)."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any

from fastapi import APIRouter, Body, Request, Response
from fastapi.responses import JSONResponse

from sentence_reading.llm.tts import CURATED_VOICES, synthesize_mp3, tts_available
from sentence_reading.llm.tts_speak import align_display_to_spoken, spoken_text_for_tts
from sentence_reading.llm.tts_speak_policy import speak_norm_version

router = APIRouter(tags=["tts"])

_PaidDenied = Callable[[Request], Response | None]
_paid_access_denied: _PaidDenied | None = None


def bind(*, paid_access_denied: _PaidDenied) -> None:
    """Wire app.py auth helper once at startup (avoids circular imports)."""
    global _paid_access_denied
    _paid_access_denied = paid_access_denied


@router.get("/api/tts/voices")
def tts_voices() -> dict:
    """UI용 추천 보이스 목록."""
    return {
        "ok": True,
        "available": tts_available(),
        "voices": CURATED_VOICES,
        "default_voice": "en-US-Neural2-D",
        "default_rate": 1.0,
        "rate_min": 0.5,
        "rate_max": 2.2,
    }


def _paper_speak_terms(cache_id: object) -> dict[str, str] | None:
    """design/343 — this paper's verified compound names, or None.

    The route only ever knew the text, so the paper's own names could not reach it.
    `cache_id` is optional: without it the reading is exactly what it was before, so
    an older client keeps working.
    """
    key = str(cache_id or "").strip()
    if not key:
        return None
    try:
        from sentence_reading.cache.paper_cache import load_cached_session

        loaded = load_cached_session(key, load_images=False)
    except Exception:  # noqa: BLE001
        return None
    if not loaded:
        return None
    terms = getattr(loaded[0], "speak_terms", None)
    return dict(terms) if isinstance(terms, dict) and terms else None


@router.post("/api/tts")
async def tts_synthesize(request: Request, payload: dict = Body(...)) -> Response:
    """현재 문장 plain text → MP3."""
    if _paid_access_denied is not None:
        denied = _paid_access_denied(request)
        if denied is not None:
            return denied
    if not tts_available():
        return JSONResponse(
            status_code=503,
            content={
                "ok": False,
                "error": "tts_unavailable",
                "message": "Cloud TTS 자격 증명이 없습니다.",
            },
        )
    text = spoken_text_for_tts(
        str(payload.get("text") or ""),
        terms=_paper_speak_terms(payload.get("cache_id")),
    )
    voice = str(payload.get("voice") or "").strip() or None
    if voice in ("undefined", "null", "None"):
        voice = None
    try:
        rate = float(payload.get("speaking_rate", 1.0))
    except (TypeError, ValueError):
        rate = 1.0
    if not text.strip():
        return JSONResponse(
            status_code=400,
            content={
                "ok": False,
                "error": "empty_text",
                "message": "읽을 문장이 없습니다.",
            },
        )
    try:
        audio = await asyncio.to_thread(
            synthesize_mp3, text, voice=voice, speaking_rate=rate
        )
    except ValueError as exc:
        code = str(exc) or "bad_request"
        return JSONResponse(
            status_code=400,
            content={"ok": False, "error": code, "message": str(exc)},
        )
    except Exception as exc:  # noqa: BLE001
        return JSONResponse(
            status_code=502,
            content={
                "ok": False,
                "error": "tts_failed",
                "message": str(exc),
            },
        )
    return Response(content=audio, media_type="audio/mpeg")


@router.post("/api/tts/spoken")
async def tts_spoken(request: Request, payload: dict = Body(...)) -> dict[str, Any]:
    """design/212 — display/plain → spoken form + speak_norm_version (no audio)."""
    if _paid_access_denied is not None:
        denied = _paid_access_denied(request)
        if denied is not None:
            return denied  # type: ignore[return-value]
    raw = str((payload or {}).get("text") or "")
    spoken = spoken_text_for_tts(
        raw, terms=_paper_speak_terms((payload or {}).get("cache_id"))
    )
    if not spoken.strip():
        return {
            "ok": False,
            "error": "empty_text",
            "message": "읽을 문장이 없습니다.",
        }
    return {
        "ok": True,
        "spoken": spoken,
        "speak_norm_version": speak_norm_version(),
        "spans": align_display_to_spoken(raw),
    }
