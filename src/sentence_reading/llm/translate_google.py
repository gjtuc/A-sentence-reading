"""
무엇을: Google Cloud Translation API bulk 영→한 (design/153).
왜: Gemini 다중 호출 대비 비용·속도 — ingest bulk + 선택 Gemini 후처리.
다음에: 용어집(glossary) · NMT 커스텀 모델.
"""

from __future__ import annotations

import logging
import os
from functools import lru_cache

from sentence_reading.llm.env import load_asr_env, tts_credentials_available
from sentence_reading.llm.gcs_sync import running_on_gcp

log = logging.getLogger(__name__)

_BATCH_MAX = 128
_LOCATION = "global"


def _project_id() -> str | None:
    load_asr_env()
    for key in ("GOOGLE_CLOUD_PROJECT", "GCP_PROJECT", "ASR_GCP_PROJECT"):
        val = (os.environ.get(key) or "").strip()
        if val:
            return val
    try:
        import google.auth

        _, project = google.auth.default()
        return (project or "").strip() or None
    except Exception:  # noqa: BLE001
        return None


def google_translate_available() -> bool:
    """ADC 또는 GOOGLE_APPLICATION_CREDENTIALS + project id."""
    if not _project_id():
        return False
    return tts_credentials_available() or running_on_gcp()


@lru_cache(maxsize=1)
def _client():
    from google.cloud import translate_v3 as translate

    load_asr_env()
    return translate.TranslationServiceClient()


def _parent() -> str | None:
    pid = _project_id()
    if not pid:
        return None
    return f"projects/{pid}/locations/{_LOCATION}"


def translate_batch_en_to_ko(texts: list[str]) -> list[str | None]:
    """
    순서 유지 bulk 번역. 빈 입력은 None.
    실패 시 해당 청크 항목 None (fail-soft).
    """
    if not texts:
        return []

    parent = _parent()
    if not parent:
        return [None] * len(texts)

    results: list[str | None] = [None] * len(texts)
    pending: list[tuple[int, str]] = []
    for i, raw in enumerate(texts):
        plain = (raw or "").strip()
        if plain:
            pending.append((i, plain))

    if not pending:
        return results

    client = _client()
    for offset in range(0, len(pending), _BATCH_MAX):
        chunk = pending[offset : offset + _BATCH_MAX]
        indices = [item[0] for item in chunk]
        contents = [item[1] for item in chunk]
        try:
            response = client.translate_text(
                request={
                    "parent": parent,
                    "contents": contents,
                    "mime_type": "text/plain",
                    "source_language_code": "en",
                    "target_language_code": "ko",
                }
            )
            for j, trans in enumerate(response.translations):
                if j >= len(indices):
                    break
                ko = (getattr(trans, "translated_text", None) or "").strip()
                results[indices[j]] = ko or None
        except Exception as exc:  # noqa: BLE001
            log.warning("google translate batch failed: %s", exc)

    return results


def translate_one_en_to_ko(text: str) -> str | None:
    batch = translate_batch_en_to_ko([text])
    return batch[0] if batch else None


def clear_google_translate_client_for_tests() -> None:
    _client.cache_clear()
