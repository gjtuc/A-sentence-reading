"""design/475 — a spoken AI question, written down with the sentence as context."""

from __future__ import annotations

import asyncio
from collections.abc import Callable

from fastapi import APIRouter, File, Form, Request, Response, UploadFile
from fastapi.responses import JSONResponse

from sentence_reading.llm import voice_question

router = APIRouter(tags=["voice_ask"])

_PaidDenied = Callable[[Request], Response | None]
_paid_access_denied: _PaidDenied | None = None


def bind(*, paid_access_denied: _PaidDenied) -> None:
    """Wire app.py auth helper once at startup (avoids circular imports)."""
    global _paid_access_denied
    _paid_access_denied = paid_access_denied


def _emit(*, ok: bool, code: str, details: dict) -> None:
    try:
        from sentence_reading.llm.evidence_bus import emit as eb_emit

        eb_emit(
            "voice_ask_transcribe",
            source="server",
            route="ask_voice",
            ok=ok,
            code=code,
            details=details,
        )
    except Exception:  # noqa: BLE001
        return


@router.post("/api/ask/voice")
async def ask_voice(
    request: Request,
    file: UploadFile = File(...),
    sentence: str = Form(""),
):
    if _paid_access_denied is not None:
        denied = _paid_access_denied(request)
        if denied is not None:
            return denied
    try:
        data = await file.read()
    except Exception:  # noqa: BLE001
        return JSONResponse(
            status_code=400, content={"ok": False, "error": "read_failed"}
        )
    mime = file.content_type or ""
    out = await asyncio.to_thread(
        voice_question.transcribe_question, data, mime=mime, sentence=sentence
    )
    ok = out.code == "ok"
    _emit(
        ok=ok,
        code=out.code,
        details={
            "audio_bytes": len(data),
            "mime": voice_question.audio_mime(mime),
            "sentence_chars": len(sentence or ""),
            "text_chars": len(out.text),
            "ms": out.ms,
        },
    )
    if not ok:
        return JSONResponse(
            status_code=413 if out.code == "audio_too_large" else 502,
            content={"ok": False, "error": out.code},
        )
    return {"ok": True, "text": out.text, "ms": out.ms}
