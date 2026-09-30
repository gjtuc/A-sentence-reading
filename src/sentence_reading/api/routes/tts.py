"""design/255 Phase 1 — TTS domain router (voices / synthesize / spoken)."""

from __future__ import annotations

import asyncio
import re
from collections.abc import Callable
from typing import Any

from fastapi import APIRouter, Body, Request, Response
from fastapi.responses import JSONResponse

from sentence_reading.llm.tts import CURATED_VOICES, synthesize_mp3, tts_available
from sentence_reading.llm.tts_speak import align_display_report, spoken_text_for_tts
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


def _attach_sound_ref(spoken: str, spans: list) -> tuple[str, int]:
    """Fill `spans[].phone` from the cached reference, or ask for one.

    Never raises and never blocks. A missing reference leaves every `phone`
    empty, which is what the scorer already treats as `sound_ref_missing`, so
    the worst case is the behaviour design/368 left behind.
    """
    from sentence_reading.llm.sound_reference import (
        attach_sounds,
        reference_for,
        request_build,
        strip_ranges,
    )

    code, filled = "none", 0
    try:
        got = reference_for(spoken, allow_build=False)
        if got is None:
            code = request_build(spoken)
        else:
            filled = attach_sounds(spans, got)
            code = "ready" if filled else "empty"
    except Exception as exc:  # noqa: BLE001
        code = re.sub(r"[^a-z0-9]+", "_", type(exc).__name__.lower())[:40] or "failed"
    finally:
        # Every span carries the key even when there is no reference, so a
        # half-written response cannot be mistaken for a scored one.
        for span in spans if isinstance(spans, list) else []:
            if isinstance(span, dict):
                span.setdefault("phone", "")
        if isinstance(spans, list):
            strip_ranges([s for s in spans if isinstance(s, dict)])
    return code, filled


def _emit_spoken_align(
    payload: dict,
    spoken: str,
    report: dict[str, object],
    spans: object,
    sound_code: str = "none",
    sound_n: int = 0,
) -> None:
    """Counts and a short code only. No sentence text."""
    try:
        from sentence_reading.llm.evidence_bus import emit as eb_emit
    except Exception:  # noqa: BLE001
        return
    code = str(report.get("code") or "unknown")
    span_list = spans if isinstance(spans, list) else []
    pos = 0
    for item in span_list:
        if (
            isinstance(item, dict)
            and int(item.get("weight") or 0) > 0
            and int(item.get("end") or 0) > int(item.get("start") or 0)
        ):
            pos += 1
    try:
        token_i = int(report.get("token_i") or -1)
    except (TypeError, ValueError):
        token_i = -1
    try:
        cursor = int(report.get("cursor") or -1)
    except (TypeError, ValueError):
        cursor = -1
    try:
        display_chars = int(report.get("display_chars") or 0)
    except (TypeError, ValueError):
        display_chars = 0
    try:
        align_spoken = int(report.get("spoken_chars") or 0)
    except (TypeError, ValueError):
        align_spoken = 0
    def _num(key: str, default: int = -1) -> int:
        try:
            return int(report.get(key) if report.get(key) is not None else default)
        except (TypeError, ValueError):
            return default

    def _shape(key: str) -> str:
        raw = str(report.get(key) or "none").strip().lower()
        if raw and re.match(r"^[a-z][a-z0-9_]{0,63}$", raw):
            return raw
        return "none"

    def _snake(raw: object) -> str:
        text = str(raw or "none").strip().lower()
        if text and re.match(r"^[a-z][a-z0-9_]{0,63}$", text):
            return text
        return "none"

    eb_emit(
        "practice_skill_align",
        source="server",
        cache_id=str((payload or {}).get("cache_id") or ""),
        route="tts_spoken",
        ok=code == "ok",
        code=code,
        details={
            "phase": "server_align",
            "align_code": code,
            "span_n": len(span_list),
            "pos_span_n": pos,
            "align_token_i": token_i,
            "align_cursor": cursor,
            "display_chars": display_chars,
            "spoken_chars": len(spoken),
            "align_spoken_chars": align_spoken,
            "token_len": _num("token_len"),
            "piece_len": _num("piece_len"),
            "differ_at": _num("differ_at"),
            "token_shape": _shape("token_shape"),
            "piece_class": _shape("piece_class"),
            "full_class": _shape("full_class"),
            "gap_len": _num("gap_len"),
            "gap_shape": _shape("gap_shape"),
            "matched_n": _num("matched_n", 0),
            "tail_n": _num("tail_n", 0),
            "renamed_n": _num("renamed_n", 0),
            # design/368 — the phone_* counts described eSpeak's reading of the
            # spelling. There is no dictionary in this route any more.
            "phone_code": "espeak_cut_368",
            # design/371 — how many printed words came back with a reference
            # sound, and why the rest did not. `queued` and `building` mean the
            # reading after this one scores; anything else is a fault.
            "sound_ref_code": _snake(sound_code),
            "sound_ref_n": int(sound_n),
            **_sound_ref_counts(),
        },
    )


def _sound_ref_counts() -> dict[str, object]:
    try:
        from sentence_reading.llm.sound_reference import build_report

        return build_report()
    except Exception:  # noqa: BLE001
        return {}


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
    report = align_display_report(raw, spoken=spoken, with_spoken_range=True)
    spans = report["spans"] if isinstance(report["spans"], list) else []
    # design/371 — the sounds a printed word is judged against. design/368 took
    # them away from eSpeak, which read a spelling out of a dictionary rather
    # than listening to a voice, and left the field empty. They come from the
    # native audio now, built from the spoken form so a printed `nm` is asked
    # for as `nanometers`. A build is far too slow to hold this call on, so the
    # cache is served and a miss is asked for in the background.
    sound_code, sound_n = _attach_sound_ref(spoken, spans)
    _emit_spoken_align(payload, spoken, report, spans, sound_code, sound_n)
    return {
        "ok": True,
        "spoken": spoken,
        "speak_norm_version": speak_norm_version(),
        "spans": spans,
        "sound_ref_code": sound_code,
        "sound_ref_n": sound_n,
        "align_code": report["code"],
        "align_token_i": report["token_i"],
        "align_cursor": report["cursor"],
        "align_display_chars": report["display_chars"],
        "align_spoken_chars": report["spoken_chars"],
        "align_token_len": report["token_len"],
        "align_piece_len": report["piece_len"],
        "align_differ_at": report["differ_at"],
        "align_token_shape": report["token_shape"],
        "align_piece_class": report["piece_class"],
        "align_full_class": report["full_class"],
        "align_gap_len": report["gap_len"],
        "align_gap_shape": report["gap_shape"],
        "align_matched_n": report["matched_n"],
        "align_tail_n": report["tail_n"],
        "align_renamed_n": report["renamed_n"],
    }
