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
