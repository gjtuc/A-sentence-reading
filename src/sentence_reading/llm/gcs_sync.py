"""
무엇을: GCS 동기화 — TTS 정속 캐시 upload/download (노트 object 경로는 예약).
왜: 다른 PC에서 같은 TTS 캐시를 이어 쓰기 (design/17).
자격: GOOGLE_APPLICATION_CREDENTIALS (TTS와 동일 SA 권장).
환경: ASR_GCS_BUCKET · ASR_GCS_PREFIX(기본 asr)
개인 흔적: personal_object_name → {prefix}/users/{uid}/… (design/22)
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from sentence_reading.llm.env import load_asr_env

log = logging.getLogger(__name__)

_SAFE_SEGMENT = re.compile(r"^[A-Za-z0-9._\-]+$")
_SAFE_REL = re.compile(r"^[A-Za-z0-9._\-]+(?:/[A-Za-z0-9._\-]+)*$")


@dataclass(frozen=True)
class GcsConfig:
    bucket: str
    prefix: str
    enabled: bool


def gcs_config() -> GcsConfig:
    load_asr_env()
    bucket = (os.environ.get("ASR_GCS_BUCKET") or "").strip()
    prefix = (os.environ.get("ASR_GCS_PREFIX") or "asr").strip().strip("/")
    # WHY: `.` / `..` 세그먼트는 문자클래스에 걸려도 경로 탈출 — 명시 거부
    bad_prefix = (
        not prefix
        or any(seg in ("", ".", "..") for seg in prefix.split("/"))
        or not _SAFE_REL.match(prefix)
    )
    if bad_prefix:
        prefix = "asr"
    return GcsConfig(bucket=bucket, prefix=prefix, enabled=bool(bucket))


def object_name(*parts: str) -> str | None:
    """
    prefix + parts → full object name.
    예: object_name("tts_cache", "abc.mp3") → asr/tts_cache/abc.mp3
    """
    cfg = gcs_config()
    segs: list[str] = []
    for p in parts:
        if p is None:
            return None
        piece = str(p).strip().replace("\\", "/").strip("/")
        if not piece:
            return None
        for seg in piece.split("/"):
            if not seg or seg in (".", "..") or not _SAFE_SEGMENT.match(seg):
                return None
            segs.append(seg)
    if not segs:
        return None
    return f"{cfg.prefix}/{'/'.join(segs)}"


def personal_object_name(*parts: str) -> str | None:
    """
    로그인 UID 가 있으면 {prefix}/users/{uid}/…
    없으면(레거시·auth 미설정) {prefix}/…
    auth 켜졌는데 UID 없으면 None (호출측이 동기화 skip/401).
    """
    from sentence_reading.llm.auth_google import (
        auth_enabled,
        current_gcs_uid,
    )

    uid = current_gcs_uid()
    if uid:
        return object_name("users", uid, *parts)
    if auth_enabled():
        return None
    return object_name(*parts)


def tts_cache_object(cache_key: str) -> str | None:
    """TTS 정속 캐시 — 내용 주소라 유저 칸 밖(공유)에 둔다."""
    key = (cache_key or "").strip()
    if not key or not _SAFE_SEGMENT.match(key):
        return None
    return object_name("tts_cache", f"{key}.mp3")


def notes_object(paper_key: str) -> str | None:
    """논문별 노트 조각 경로(예약). 전체 store는 notes_gcs.notes_store_object."""
    raw = (paper_key or "").strip()
    if not raw:
        return None
    safe = re.sub(r"[^A-Za-z0-9._\-]+", "_", raw).strip("_")
    if not safe or len(safe) > 180:
        return None
    return personal_object_name("notes", f"{safe}.json")


def _assert_under_prefix(full_name: str) -> str | None:
    cfg = gcs_config()
    name = (full_name or "").strip()
    if not name.startswith(cfg.prefix + "/") or not _SAFE_REL.match(name):
        return None
    if any(seg in ("", ".", "..") for seg in name.split("/")):
        return None
    return name


@lru_cache(maxsize=1)
def _storage_client():
    from google.cloud import storage

    load_asr_env()
    return storage.Client()


def reset_gcs_client_cache() -> None:
    """테스트용 — 클라이언트 캐시 비움."""
    _storage_client.cache_clear()


def running_on_gcp() -> bool:
    """Cloud Run / GCP 런타임 — ADC(메타데이터 SA) 사용 가능."""
    return bool(
        (os.environ.get("K_SERVICE") or "").strip()
        or (os.environ.get("CLOUD_RUN_JOB") or "").strip()
    )


def gcs_client_ready() -> tuple[bool, str]:
    """자격·라이브러리 준비 (버킷 존재 HTTP 검증은 생략 — 비용·지연)."""
    cfg = gcs_config()
    if not cfg.enabled:
        return False, "set ASR_GCS_BUCKET to enable cloud sync"
    try:
        import google.cloud.storage  # noqa: F401
    except ImportError:
        return False, "google-cloud-storage not installed"
    cred = (os.environ.get("GOOGLE_APPLICATION_CREDENTIALS") or "").strip()
    if cred:
        if not Path(cred).is_file():
            return False, "GOOGLE_APPLICATION_CREDENTIALS file missing"
        return True, "ok"
    # WHY: Cloud Run 은 런타임 SA ADC — JSON 파일 없음 (design/25)
    if running_on_gcp():
        return True, "adc"
    return False, "GOOGLE_APPLICATION_CREDENTIALS missing"


def upload_bytes(
    full_object_name: str,
    data: bytes,
    *,
    content_type: str = "application/octet-stream",
    meter: bool = True,
) -> bool:
    """bytes → GCS. 실패 시 False (호출측 TTS를 막지 않음)."""
    cfg = gcs_config()
    if not cfg.enabled:
        return False
    if not isinstance(data, (bytes, bytearray)) or len(data) == 0:
        return False
    name = _assert_under_prefix(full_object_name)
    if not name:
        return False
    ready, msg = gcs_client_ready()
    if not ready:
        log.debug("gcs upload skipped: %s", msg)
        return False
    try:
        client = _storage_client()
        blob = client.bucket(cfg.bucket).blob(name)
        payload = bytes(data)
        blob.upload_from_string(payload, content_type=content_type)
        if meter:
            try:
                from sentence_reading.llm.usage_meter import record

                record(gcs_ops=1, gcs_upload_bytes=len(payload))
            except Exception:  # noqa: BLE001
                pass
        return True
    except Exception as exc:  # noqa: BLE001
        log.warning("gcs upload failed %s: %s", name, exc)
        return False


def download_bytes(full_object_name: str, *, meter: bool = True) -> bytes | None:
    """GCS → bytes. miss/실패면 None."""
    cfg = gcs_config()
    if not cfg.enabled:
        return None
    name = _assert_under_prefix(full_object_name)
    if not name:
        return None
    ready, msg = gcs_client_ready()
    if not ready:
        log.debug("gcs download skipped: %s", msg)
        return None
    try:
        client = _storage_client()
        blob = client.bucket(cfg.bucket).blob(name)
        if not blob.exists():
            return None
        data = blob.download_as_bytes()
        if data and meter:
            try:
                from sentence_reading.llm.usage_meter import record

                record(gcs_ops=1, gcs_download_bytes=len(data))
            except Exception:  # noqa: BLE001
                pass
        return data if data else None
    except Exception as exc:  # noqa: BLE001
        log.warning("gcs download failed %s: %s", name, exc)
        return None


def blob_exists(full_object_name: str) -> bool:
    cfg = gcs_config()
    if not cfg.enabled:
        return False
    name = _assert_under_prefix(full_object_name)
    if not name:
        return False
    ready, _ = gcs_client_ready()
    if not ready:
        return False
    try:
        return bool(_storage_client().bucket(cfg.bucket).blob(name).exists())
    except Exception:  # noqa: BLE001
        return False


def delete_bytes(full_object_name: str) -> bool:
    """GCS object 삭제. 없거나 실패면 False (호출측 best-effort)."""
    cfg = gcs_config()
    if not cfg.enabled:
        return False
    name = _assert_under_prefix(full_object_name)
    if not name:
        return False
    ready, msg = gcs_client_ready()
    if not ready:
        log.debug("gcs delete skipped: %s", msg)
        return False
    try:
        blob = _storage_client().bucket(cfg.bucket).blob(name)
        if blob.exists():
            blob.delete()
        return True
    except Exception as exc:  # noqa: BLE001
        log.warning("gcs delete failed %s: %s", name, exc)
        return False


def gcs_status() -> dict[str, Any]:
    cfg = gcs_config()
    ready, message = gcs_client_ready()
    from sentence_reading.llm.auth_google import auth_status_fields, current_gcs_uid
    from sentence_reading.llm.notes_gcs import notes_gcs_status_fields
    from sentence_reading.llm.voice_gcs import voice_gcs_status_fields

    out: dict[str, Any] = {
        "enabled": cfg.enabled,
        "bucket": cfg.bucket or None,
        "prefix": cfg.prefix,
        "ready": bool(cfg.enabled and ready),
        "tts_cache_sync": True,
        "message": message if cfg.enabled else "set ASR_GCS_BUCKET to enable cloud sync",
        "user_prefix": (
            f"{cfg.prefix}/users/{current_gcs_uid()}"
            if current_gcs_uid()
            else None
        ),
    }
    out.update(auth_status_fields())
    out.update(notes_gcs_status_fields())
    out.update(voice_gcs_status_fields())
    from sentence_reading.llm.papers_gcs import papers_gcs_status_fields

    out.update(papers_gcs_status_fields())
    return out

