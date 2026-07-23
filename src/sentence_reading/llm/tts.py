"""
무엇을: Cloud Text-to-Speech 로 문장 → MP3.
왜: 문장 클릭 TTS — 화면은 그대로, 소리만 (하이라이트 없음).
다음에: 캐시 LRU. 말할 말 정규화는 tts_speak.spoken_text_for_tts (API에서 적용).
"""

from __future__ import annotations

import hashlib
from functools import lru_cache
from pathlib import Path

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
    import os

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
    import os

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


@lru_cache(maxsize=1)
def _client():
    from google.cloud import texttospeech

    # WHY: GOOGLE_APPLICATION_CREDENTIALS 는 load_asr_env 로 이미 설정
    load_asr_env()
    return texttospeech.TextToSpeechClient()


def _language_code(voice_name: str) -> str:
    # en-US-Neural2-D → en-US
    parts = (voice_name or "").split("-")
    if len(parts) >= 2:
        return f"{parts[0]}-{parts[1]}"
    return "en-US"


def synthesize_mp3(
    text: str,
    *,
    voice: str | None = None,
    speaking_rate: float | None = None,
) -> bytes:
    """plain text → MP3 bytes. 실패 시 예외."""
    from google.cloud import texttospeech

    plain = (text or "").strip()
    if not plain:
        raise ValueError("empty_text")
    if len(plain) > 4500:
        plain = plain[:4500]

    settings = default_tts_settings()
    voice_name = (voice or settings["voice"]).strip() or _DEFAULT_VOICE
    rate = settings["speaking_rate"] if speaking_rate is None else float(speaking_rate)
    rate = max(0.5, min(2.2, rate))

    if not tts_available():
        raise RuntimeError("tts_credentials_missing")

    client = _client()
    synthesis_input = texttospeech.SynthesisInput(text=plain)
    voice_params = texttospeech.VoiceSelectionParams(
        language_code=_language_code(voice_name),
        name=voice_name,
    )
    audio_config = texttospeech.AudioConfig(
        audio_encoding=texttospeech.AudioEncoding.MP3,
        speaking_rate=rate,
    )
    response = client.synthesize_speech(
        input=synthesis_input,
        voice=voice_params,
        audio_config=audio_config,
    )
    return response.audio_content


def cache_key(text: str, voice: str, rate: float) -> str:
    raw = f"{voice}|{rate:.2f}|{text}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:24]
