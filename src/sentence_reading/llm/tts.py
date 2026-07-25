"""
무엇을: Cloud Text-to-Speech 로 문장 → MP3 (+ 정속 디스크 캐시).
왜: 문장 클릭 TTS — 화면은 그대로, 소리만 (하이라이트 없음).
다음에: GCS 동기화. 배속은 클라이언트 WSOLA/playbackRate (design/17).
"""

from __future__ import annotations

import hashlib
import os
from functools import lru_cache
from pathlib import Path

from sentence_reading.cache.paper_cache import project_root
from sentence_reading.llm.env import load_asr_env

# 논문 영어 기본 — UI에서 변경 가능
_DEFAULT_VOICE = "en-US-Neural2-D"
_DEFAULT_RATE = 1.0
_VOICE_CHOICES = (
    ("en-US-Neural2-A", "en-US Neural2 A (여성)"),
    ("en-US-Neural2-C", "en-US Neural2 C (여성)"),
    ("en-US-Neural2-D", "en-US Neural2 D (남성)"),
    ("en-US-Neural2-E", "en-US Neural2 E (여성)"),
    ("en-US-Neural2-F", "en-US Neural2 F (여성)"),
    ("en-US-Neural2-G", "en-US Neural2 G (여성)"),
    ("en-US-Neural2-H", "en-US Neural2 H (여성)"),
    ("en-US-Neural2-I", "en-US Neural2 I (남성)"),
    ("en-US-Neural2-J", "en-US Neural2 J (남성)"),
    ("en-GB-Neural2-A", "en-GB Neural2 A (여성)"),
    ("en-GB-Neural2-B", "en-GB Neural2 B (남성)"),
    ("en-GB-Neural2-C", "en-GB Neural2 C (여성)"),
    ("en-GB-Neural2-D", "en-GB Neural2 D (남성)"),
    ("en-AU-Neural2-A", "en-AU Neural2 A (여성)"),
    ("en-AU-Neural2-B", "en-AU Neural2 B (남성)"),
    ("en-AU-Neural2-C", "en-AU Neural2 C (여성)"),
    ("en-AU-Neural2-D", "en-AU Neural2 D (남성)"),
    ("en-IN-Neural2-A", "en-IN Neural2 A (여성)"),
    ("en-IN-Neural2-B", "en-IN Neural2 B (남성)"),
    ("en-IN-Neural2-C", "en-IN Neural2 C (남성)"),
    ("en-IN-Neural2-D", "en-IN Neural2 D (여성)"),
)


def tts_credentials_path() -> Path | None:
    load_asr_env()
    raw = (os.environ.get("GOOGLE_APPLICATION_CREDENTIALS") or "").strip()
    if not raw:
        return None
    path = Path(raw)
    return path if path.is_file() else None


def tts_available() -> bool:
    return tts_credentials_path() is not None


def list_voice_choices() -> list[dict[str, str]]:
    return [{"id": vid, "label": label} for vid, label in _VOICE_CHOICES]


# API / UI 호환 이름
CURATED_VOICES = list_voice_choices()


def default_tts_settings() -> dict:
    load_asr_env()
    voice = (os.environ.get("ASR_TTS_VOICE") or _DEFAULT_VOICE).strip()
    try:
        rate = float(os.environ.get("ASR_TTS_RATE") or _DEFAULT_RATE)
    except ValueError:
        rate = _DEFAULT_RATE
    rate = max(0.5, min(2.2, rate))
    known = {v for v, _ in _VOICE_CHOICES}
    if voice not in known:
        voice = _DEFAULT_VOICE
    return {"voice": voice, "speaking_rate": rate}


def tts_cache_dir() -> Path:
    """정속 MP3 캐시 디렉터리 (로컬). GCS는 후속."""
    load_asr_env()
    raw = (os.environ.get("ASR_TTS_CACHE_DIR") or "").strip()
    if raw:
        return Path(raw)
    return project_root() / "data" / "tts_cache"


def cache_key(text: str, voice: str, rate: float = 1.0) -> str:
    # WHY: 배속은 클라이언트 — 캐시 키는 정속(1.0) 기준
    _ = rate
    raw = f"{voice}|1.00|{text}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:24]


@lru_cache(maxsize=1)
def _client():
    from google.cloud import texttospeech

    load_asr_env()
    return texttospeech.TextToSpeechClient()


def _language_code(voice_name: str) -> str:
    parts = (voice_name or "").split("-")
    if len(parts) >= 2:
        return f"{parts[0]}-{parts[1]}"
    return "en-US"


def _synthesize_uncached(plain: str, voice_name: str) -> bytes:
    """Cloud TTS — 항상 정속(1.0)."""
    from google.cloud import texttospeech

    client = _client()
    synthesis_input = texttospeech.SynthesisInput(text=plain)
    voice_params = texttospeech.VoiceSelectionParams(
        language_code=_language_code(voice_name),
        name=voice_name,
    )
    audio_config = texttospeech.AudioConfig(
        audio_encoding=texttospeech.AudioEncoding.MP3,
        speaking_rate=1.0,
    )
    response = client.synthesize_speech(
        input=synthesis_input,
        voice=voice_params,
        audio_config=audio_config,
    )
    return response.audio_content


def synthesize_mp3(
    text: str,
    *,
    voice: str | None = None,
    speaking_rate: float | None = None,
) -> bytes:
    """
    plain text → MP3 bytes (정속 캐시).
    speaking_rate 인자는 호환용으로 받지만 합성에는 쓰지 않음 —
    배속은 프론트 WSOLA / playbackRate.
    """
    _ = speaking_rate  # API 호환 — 의도적 미사용
    plain = (text or "").strip()
    if not plain:
        raise ValueError("empty_text")
    if len(plain) > 4500:
        plain = plain[:4500]

    settings = default_tts_settings()
    voice_name = (voice or settings["voice"]).strip() or _DEFAULT_VOICE

    if not tts_available():
        raise RuntimeError("tts_credentials_missing")

    key = cache_key(plain, voice_name, 1.0)
    cache_path = tts_cache_dir() / f"{key}.mp3"
    try:
        if cache_path.is_file() and cache_path.stat().st_size > 0:
            return cache_path.read_bytes()
    except OSError:
        pass

    audio = _synthesize_uncached(plain, voice_name)
    try:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_bytes(audio)
    except OSError:
        pass
    return audio
