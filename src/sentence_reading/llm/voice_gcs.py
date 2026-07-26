"""
무엇을: 목소리 blob GCS upload/download.
왜: 노트 store의 blobKey 메타가 PC 간에 재생 가능하도록 (design/17).
object: {prefix}/voice/{sha256(blobKey)}.bin
"""

from __future__ import annotations

import hashlib
import logging
from typing import Any

from sentence_reading.llm.gcs_sync import (
    download_bytes,
    gcs_client_ready,
    gcs_config,
    object_name,
    upload_bytes,
)

log = logging.getLogger(__name__)

VOICE_BLOB_MAX_BYTES = 5_000_000
VOICE_BLOB_KEY_MAX = 500


def voice_blob_digest(blob_key: str) -> str | None:
    raw = (blob_key or "").strip()
    if not raw or len(raw) > VOICE_BLOB_KEY_MAX:
        return None
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def voice_blob_object(blob_key: str) -> str | None:
    digest = voice_blob_digest(blob_key)
    if not digest:
        return None
    return object_name("voice", f"{digest}.bin")


def upload_voice_blob(
    blob_key: str,
    data: bytes,
    *,
    content_type: str = "application/octet-stream",
) -> bool:
    if not isinstance(data, (bytes, bytearray)) or len(data) == 0:
        return False
    if len(data) > VOICE_BLOB_MAX_BYTES:
        log.warning("voice blob too large: %s bytes", len(data))
        return False
    obj = voice_blob_object(blob_key)
    if not obj:
        return False
    return upload_bytes(obj, bytes(data), content_type=content_type or "application/octet-stream")


def download_voice_blob(blob_key: str) -> bytes | None:
    obj = voice_blob_object(blob_key)
    if not obj:
        return None
    data = download_bytes(obj)
    if data and len(data) > VOICE_BLOB_MAX_BYTES:
        return None
    return data


def voice_gcs_status_fields() -> dict[str, Any]:
    ready, _ = gcs_client_ready()
    cfg = gcs_config()
    return {
        "voice_blob_sync": True,
        "voice_max_bytes": VOICE_BLOB_MAX_BYTES,
        "voice_ready": bool(cfg.enabled and ready),
    }
