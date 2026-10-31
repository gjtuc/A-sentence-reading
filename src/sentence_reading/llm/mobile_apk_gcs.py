"""
design/161 — mobile release APK in GCS (private bucket; served via Cloud Run proxy).

object: {prefix}/mobile/sentence-reading-latest.apk
"""

from __future__ import annotations

import os
from collections.abc import Iterator

from sentence_reading.llm.gcs_sync import (
    download_bytes,
    gcs_client_ready,
    gcs_config,
    object_name,
)

MOBILE_APK_FILENAME = "sentence-reading-latest.apk"
# design/495 — the PC helper (scripts/build_helper_exe.py uploads it).
HELPER_EXE_FILENAME = "sentence-reading-helper.exe"
# design/497 — Partner Center > Product identity > Store ID, once the helper is listed.
HELPER_STORE_ID = ""


def helper_store_url() -> str | None:
    """Microsoft Store page of the helper; ASR_HELPER_STORE_URL overrides for a trial."""
    override = (os.environ.get("ASR_HELPER_STORE_URL") or "").strip()
    if override:
        return override
    return f"https://apps.microsoft.com/detail/{HELPER_STORE_ID}" if HELPER_STORE_ID else None


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


def helper_exe_object() -> str | None:
    return object_name("mobile", HELPER_EXE_FILENAME)


def iter_helper_exe_chunks(*, chunk_size: int = 1024 * 1024) -> Iterator[bytes] | None:
    return iter_mobile_apk_chunks(chunk_size=chunk_size, obj=helper_exe_object())


def iter_mobile_apk_chunks(
    *, chunk_size: int = 1024 * 1024, obj: str | None = None
) -> Iterator[bytes] | None:
    """Stream APK from GCS; None when missing/unavailable."""
    obj = obj or mobile_apk_object()
    if not obj:
        return None
    ready, _msg = mobile_apk_ready()
    if not ready:
        return None
    try:
        from sentence_reading.llm.gcs_sync import _storage_client

        cfg = gcs_config()
        blob = _storage_client().bucket(cfg.bucket).blob(obj)
        if not blob.exists():
            return None

        def _gen() -> Iterator[bytes]:
            with blob.open("rb") as fh:
                while True:
                    chunk = fh.read(chunk_size)
                    if not chunk:
                        break
                    yield chunk

        return _gen()
    except Exception:  # noqa: BLE001
        return None
