"""
무엇을: 발음 표본(design/364) 녹음과 메타를 GCS 개인 칸에 저장.
왜: 지금 /api/stt/recognize 는 오디오를 듣고 바로 버린다. 채점 방식을 바꿀
    때마다 같은 녹음에 다시 돌려봐야 하는데, 버리면 매번 다시 연습해야 한다.
object: {prefix}/users/{uid}/sample_takes/r{round:02d}/{line}_{stamp}.m4a (+ .json)
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import time
from typing import Any

from sentence_reading.llm.gcs_sync import (
    gcs_client_ready,
    personal_object_name,
    upload_bytes,
)

log = logging.getLogger(__name__)

SAMPLE_TAKE_MAX_BYTES = 8_000_000
SAMPLE_ROUND_MIN = 1
SAMPLE_ROUND_MAX = 10
_LINE_ID_RE = re.compile(r"^[a-z][a-z0-9_]{0,31}$")
_EXT_BY_MIME = {
    "audio/mp4": "m4a",
    "audio/m4a": "m4a",
    "audio/aac": "aac",
    "audio/mpeg": "mp3",
    "audio/wav": "wav",
    "audio/x-wav": "wav",
    "audio/webm": "webm",
    "audio/ogg": "ogg",
}


def sample_round_ok(round_n: int) -> bool:
    return SAMPLE_ROUND_MIN <= int(round_n or 0) <= SAMPLE_ROUND_MAX


def safe_line_id(raw: str | None) -> str | None:
    lid = (raw or "").strip().lower()
    return lid if _LINE_ID_RE.match(lid) else None


def take_extension(mime: str | None) -> str:
    return _EXT_BY_MIME.get((mime or "").split(";")[0].strip().lower(), "bin")


def sample_take_stem(*, round_n: int, line_id: str, audio: bytes) -> str | None:
    """`{line}_{ms}_{digest8}` — unique per take, sorts by time within a line."""
    lid = safe_line_id(line_id)
    if not lid or not sample_round_ok(round_n):
        return None
    digest = hashlib.sha256(bytes(audio or b"")).hexdigest()[:8]
    return f"{lid}_{int(time.time() * 1000)}_{digest}"


def sample_take_object(*, round_n: int, stem: str, ext: str) -> str | None:
    if not sample_round_ok(round_n) or not stem:
        return None
    return personal_object_name(
        "sample_takes", f"r{int(round_n):02d}", f"{stem}.{ext}"
    )


def save_sample_take(
    *,
    round_n: int,
    line_id: str,
    audio: bytes,
    mime: str,
    meta: dict[str, Any],
) -> dict[str, Any]:
    """Upload the take plus its sidecar. Never raises into the request path.

    Returns numbers and one snake code so a silent skip still has a reason.
    """
    out: dict[str, Any] = {
        "take_saved": 0,
        "take_bytes": len(audio or b""),
        "take_code": "none",
    }
    if not sample_round_ok(round_n):
        out["take_code"] = "bad_round"
        return out
    if not audio:
        out["take_code"] = "empty_audio"
        return out
    if len(audio) > SAMPLE_TAKE_MAX_BYTES:
        out["take_code"] = "too_large"
        return out
    stem = sample_take_stem(round_n=round_n, line_id=line_id, audio=audio)
    if not stem:
        out["take_code"] = "bad_line_id"
        return out
    ready, _ = gcs_client_ready()
    if not ready:
        out["take_code"] = "gcs_unready"
        return out
    ext = take_extension(mime)
    audio_obj = sample_take_object(round_n=round_n, stem=stem, ext=ext)
    meta_obj = sample_take_object(round_n=round_n, stem=stem, ext="json")
    if not audio_obj or not meta_obj:
        # personal_object_name returns None when auth is on but no uid is bound.
        out["take_code"] = "no_uid"
        return out
    try:
        if not upload_bytes(
            audio_obj, bytes(audio), content_type=mime or "audio/mp4"
        ):
            out["take_code"] = "audio_upload_failed"
            return out
    except Exception:  # noqa: BLE001
        out["take_code"] = "audio_upload_raised"
        return out
    payload = dict(meta)
    payload.update(
        {
            "version": 1,
            "round": int(round_n),
            "line_id": safe_line_id(line_id),
            "stem": stem,
            "audio_object": audio_obj,
            "mime": mime or "",
            "bytes": len(audio),
            "saved_at_ms": int(time.time() * 1000),
        }
    )
    raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode(
        "utf-8"
    )
    try:
        # The audio is already up; a lost sidecar leaves an unlabelled take, so
        # say so rather than reporting the take as saved.
        if not upload_bytes(meta_obj, raw, content_type="application/json"):
            out["take_code"] = "meta_upload_failed"
            return out
    except Exception:  # noqa: BLE001
        out["take_code"] = "meta_upload_raised"
        return out
    out["take_saved"] = 1
    out["take_code"] = "ok"
    return out
