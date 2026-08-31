"""
design/161 — mobile release APK in GCS (private bucket; served via Cloud Run proxy).

object: {prefix}/mobile/sentence-reading-latest.apk
"""

from __future__ import annotations

from sentence_reading.llm.gcs_sync import (
    download_bytes,
    gcs_client_ready,
    gcs_config,
    object_name,
)

MOBILE_APK_FILENAME = "sentence-reading-latest.apk"


def mobile_apk_object() -> str | None:
    return object_name("mobile", MOBILE_APK_FILENAME)


def mobile_apk_ready() -> tuple[bool, str]:
    cfg = gcs_config()
    if not cfg.enabled:
        return False, "set ASR_GCS_BUCKET to enable APK download"
    ready, msg = gcs_client_ready()
    if not ready:
        return False, msg
    return True, "ok"


def download_mobile_apk() -> bytes | None:
    obj = mobile_apk_object()
    if not obj:
        return None
    return download_bytes(obj)
