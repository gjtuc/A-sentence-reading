"""
무엇을: GCS 동기화 스캐폴드 (논문·노트·TTS·음성).
왜: 다른 PC에서 되새김질 산출물·논문을 이어 쓰기 (design/17).
다음에: 실제 upload/download · 서명 URL · 충돌 정책.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from sentence_reading.llm.env import load_asr_env


@dataclass(frozen=True)
class GcsConfig:
    bucket: str
    prefix: str
    enabled: bool


def gcs_config() -> GcsConfig:
    load_asr_env()
    bucket = (os.environ.get("ASR_GCS_BUCKET") or "").strip()
    prefix = (os.environ.get("ASR_GCS_PREFIX") or "asr").strip().strip("/")
    return GcsConfig(bucket=bucket, prefix=prefix or "asr", enabled=bool(bucket))


def gcs_status() -> dict:
    cfg = gcs_config()
    return {
        "enabled": cfg.enabled,
        "bucket": cfg.bucket or None,
        "prefix": cfg.prefix,
        "ready": False if not cfg.enabled else False,
        # WHY: 자격·버킷 검증은 후속 — 지금은 설정 존재만 보고
        "message": (
            "ASR_GCS_BUCKET set — sync not implemented yet"
            if cfg.enabled
            else "set ASR_GCS_BUCKET to enable cloud sync"
        ),
    }
