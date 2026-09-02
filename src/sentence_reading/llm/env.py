"""
무엇을: Gemini / ASR 환경변수 로드.
왜: 키는 repo에 두지 않고 Desktop/.cursor/gc_automation.env 를 읽는다.
"""

from __future__ import annotations

import os
from pathlib import Path

_DEFAULT_ENV_CANDIDATES = (
    Path(r"C:\Users\user\Desktop\.cursor\gc_automation.env"),
    Path.home() / "Desktop" / ".cursor" / "gc_automation.env",
)


def _parse_env_file(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if not path.is_file():
        return out
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        s = line.strip()
        if not s or s.startswith("#") or "=" not in s:
            continue
        key, _, val = s.partition("=")
        key = key.strip()
        val = val.strip().strip('"').strip("'")
        if key:
            out[key] = val
    return out


def load_asr_env() -> None:
    """gc_automation.env 값을 os.environ에 채운다 (이미 있으면 유지)."""
    # WHY: pytest 가 실기기 env 파일을 읽지 않게 (tests/conftest)
    if (os.environ.get("ASR_SKIP_ENV_FILE") or "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    ):
        return
    for path in _DEFAULT_ENV_CANDIDATES:
        parsed = _parse_env_file(path)
        if not parsed:
            continue
        for k, v in parsed.items():
            os.environ.setdefault(k, v)
        break


def gemini_api_key() -> str | None:
    load_asr_env()
    key = (os.environ.get("GEMINI_API_KEY") or "").strip()
    return key or None


def gemini_model() -> str:
    load_asr_env()
    # WHY: 2.0-flash 는 2026-07 기준 API에서 제거됨. stock screener 와 맞춤.
    return (os.environ.get("ASR_GEMINI_MODEL") or "gemini-2.5-flash").strip()


def gemini_available() -> bool:
    return gemini_api_key() is not None


def translate_backend() -> str:
    """google (default) | gemini — design/153."""
    load_asr_env()
    raw = (os.environ.get("ASR_TRANSLATE_BACKEND") or "google").strip().lower()
    return raw if raw in ("google", "gemini") else "google"


def translate_gemini_post() -> bool:
    """Google bulk 후 digest/harmonize 등 Gemini 후처리 (design/153)."""
    load_asr_env()
    raw = (os.environ.get("ASR_TRANSLATE_GEMINI_POST") or "1").strip().lower()
    return raw not in ("0", "false", "no", "off")


def harmonize_residual_enabled() -> bool:
    """design/169o — defer sentence/caption harmonize after ingest (default on)."""
    load_asr_env()
    raw = (os.environ.get("ASR_HARMONIZE_RESIDUAL") or "1").strip().lower()
    return raw not in ("0", "false", "no", "off")


def translate_available() -> bool:
    from sentence_reading.llm.translate_google import google_translate_available

    if translate_backend() == "gemini":
        return gemini_available()
    return google_translate_available() or gemini_available()


def azure_document_intelligence_endpoint() -> str | None:
    load_asr_env()
    raw = (os.environ.get("AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT") or "").strip().rstrip("/")
    return raw or None


def azure_document_intelligence_key() -> str | None:
    load_asr_env()
    key = (os.environ.get("AZURE_DOCUMENT_INTELLIGENCE_KEY") or "").strip()
    return key or None


def azure_document_intelligence_available() -> bool:
    return bool(
        azure_document_intelligence_endpoint() and azure_document_intelligence_key()
    )


def tts_credentials_available() -> bool:
    """Cloud Text-to-Speech 자격 — JSON 경로 또는 Cloud Run ADC."""
    load_asr_env()
    raw = (os.environ.get("GOOGLE_APPLICATION_CREDENTIALS") or "").strip()
    if raw and Path(raw).is_file():
        return True
    from sentence_reading.llm.gcs_sync import running_on_gcp

    return running_on_gcp()
