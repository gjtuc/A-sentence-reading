"""
무엇을: 짧은 연습 오디오 → 영어 전사 (Gemini · 점수 없음).
왜: 브라우저 STT 폴백 위에 서버 인식 (design/38).
다음에: 스트리밍·전용 Speech API (필요 시).
"""

from __future__ import annotations

import logging
import re
from typing import Any

from sentence_reading.llm.env import gemini_api_key, gemini_model

log = logging.getLogger(__name__)

# WHY: 연습 한 문장 녹음 — 논문 전체·장시간 업로드 차단
_MAX_BYTES = 2 * 1024 * 1024

_ALLOWED_BASE = frozenset(
    {
        "audio/webm",
        "audio/wav",
        "audio/wave",
        "audio/x-wav",
        "audio/mp4",
        "audio/mpeg",
        "audio/mp3",
        "audio/ogg",
        "audio/flac",
        "audio/x-m4a",
        "audio/aac",
    }
)

_SYSTEM = """You are a careful English speech transcriber for a researcher practicing one academic sentence.
Transcribe the spoken English into plain text only.
Output the transcript only — no quotes, no punctuation commentary, no translation, no confidence scores, no grading.
If there is no intelligible speech, output an empty string.
"""


def normalize_audio_mime(mime: str | None) -> str:
    raw = (mime or "").strip().lower()
    if not raw:
        return ""
    # WHY: Chrome 은 audio/webm;codecs=opus 형태
    return raw.split(";", 1)[0].strip()


def mime_allowed(mime: str | None) -> bool:
    base = normalize_audio_mime(mime)
    if not base:
        return False
    if base in _ALLOWED_BASE:
        return True
    # WHY: 일부 브라우저가 audio/* 변형을 보냄 — audio/ 접두만 허용
    return base.startswith("audio/") and len(base) < 64


def _clean_transcript(text: str) -> str:
    t = (text or "").strip().strip("「」\"'")
    # WHY: 모델이 Transcript: 접두를 붙이는 경우
    low = t.lower()
    for prefix in ("transcript:", "transcription:", "text:"):
        if low.startswith(prefix):
            t = t.split(":", 1)[1].strip()
            break
    t = re.sub(r"\s+", " ", t).strip()
    return t


def _response_text(response: Any) -> str:
    text = (getattr(response, "text", None) or "").strip()
    if text:
        return _clean_transcript(text)
    parts: list[str] = []
    for cand in getattr(response, "candidates", None) or []:
        content = getattr(cand, "content", None)
        for part in getattr(content, "parts", None) or []:
            if getattr(part, "thought", False):
                continue
            t = getattr(part, "text", None) or ""
            if t:
                parts.append(t)
    return _clean_transcript("".join(parts))


def recognize_english_audio(data: bytes, mime_type: str | None) -> dict[str, Any]:
    """
    Returns {ok, heard?, engine?} or {ok: False, error}.
    # INVARIANT: score / grade / accuracy 키를 넣지 않는다.
    """
    if data is None:
        return {"ok": False, "error": "empty_audio"}
    if not isinstance(data, (bytes, bytearray)):
        return {"ok": False, "error": "invalid_audio"}
    raw = bytes(data)
    if not raw:
        return {"ok": False, "error": "empty_audio"}
    if len(raw) > _MAX_BYTES:
        return {
            "ok": False,
            "error": "too_large",
            "max_bytes": _MAX_BYTES,
        }
    if not mime_allowed(mime_type):
        return {
            "ok": False,
            "error": "unsupported_mime",
            "mime": normalize_audio_mime(mime_type) or None,
        }

    if not gemini_api_key():
        return {"ok": False, "error": "gemini_unavailable"}

    mime = normalize_audio_mime(mime_type) or "audio/webm"

    from google import genai
    from google.genai import types

    client = genai.Client(api_key=gemini_api_key())
    contents = [
        types.Content(
            role="user",
            parts=[
                types.Part.from_text(
                    text="Transcribe this English speech to plain text."
                ),
                types.Part.from_bytes(data=raw, mime_type=mime),
            ],
        )
    ]
    try:
        response = client.models.generate_content(
            model=gemini_model(),
            contents=contents,
            config=types.GenerateContentConfig(
                system_instruction=_SYSTEM,
                temperature=0.1,
                max_output_tokens=1024,
            ),
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("stt recognize failed: %s", exc)
        return {
            "ok": False,
            "error": "recognize_failed",
            "message": str(exc)[:200],
        }

    try:
        from sentence_reading.llm.usage_meter import record_gemini_response

        record_gemini_response("stt_recognize", response)
    except Exception:  # noqa: BLE001
        pass

    heard = _response_text(response)
    # WHY: 무음도 ok — 비교 단계에서 empty 처리
    return {"ok": True, "heard": heard, "engine": "gemini"}
