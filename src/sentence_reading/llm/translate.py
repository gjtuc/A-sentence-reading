"""
무엇을: 학술 문장 영→한 단순 번역 (Gemini).
왜: 표시 on/off MVP · 다단계 파이프라인의 받침 (design/35).
다음에: 용어집·감수·윤문 다단계.
"""

from __future__ import annotations

import hashlib
import logging
import re
import threading
from typing import Any

from sentence_reading.llm.env import gemini_api_key, gemini_model

log = logging.getLogger(__name__)

_MAX_CHARS = 4000
_LOCK = threading.RLock()
# WHY: 같은 문장 반복(←/→) 시 호출 절약 — 프로세스 수명 캐시
_CACHE: dict[str, str] = {}
_CACHE_MAX = 256

_SYSTEM = """You translate academic English into natural Korean for a researcher reading one sentence at a time.
Output Korean only — no quotes, no English echo, no preamble.
Keep chemical formulas, symbols, and proper nouns accurate; you may keep Latin formulas as-is when clearer.
Do not add explanations or footnotes.
"""


def _plain(text: str) -> str:
    t = re.sub(r"<[^>]+>", " ", text or "")
    t = re.sub(r"\s+", " ", t).strip()
    return t


def _cache_key(plain: str) -> str:
    return hashlib.sha256(plain.encode("utf-8")).hexdigest()


def translate_en_to_ko(text: str) -> dict[str, Any]:
    """
    Returns {ok, ko?} or {ok: False, error}.
    # INVARIANT: empty / too_long / no-key 는 Gemini 를 호출하지 않는다.
    """
    plain = _plain(text)
    if not plain:
        return {"ok": False, "error": "empty"}
    if len(plain) > _MAX_CHARS:
        # WHY: 실수로 논문 전체·노트 덤프가 오면 비용·지연 폭발 방지
        return {"ok": False, "error": "too_long", "max_chars": _MAX_CHARS}

    key = _cache_key(plain)
    with _LOCK:
        hit = _CACHE.get(key)
    if hit is not None:
        return {"ok": True, "ko": hit, "cached": True}

    if not gemini_api_key():
        return {"ok": False, "error": "gemini_unavailable"}

    from google import genai
    from google.genai import types

    client = genai.Client(api_key=gemini_api_key())
    response = client.models.generate_content(
        model=gemini_model(),
        contents=f"Translate to Korean:\n\n{plain}",
        config=types.GenerateContentConfig(
            system_instruction=_SYSTEM,
            temperature=0.2,
            max_output_tokens=2048,
        ),
    )
    try:
        from sentence_reading.llm.usage_meter import record_gemini_response

        record_gemini_response(plain, response)
    except Exception:  # noqa: BLE001
        pass

    ko = (getattr(response, "text", None) or "").strip()
    if not ko:
        parts: list[str] = []
        for cand in getattr(response, "candidates", None) or []:
            content = getattr(cand, "content", None)
            for part in getattr(content, "parts", None) or []:
                if getattr(part, "thought", False):
                    continue
                t = getattr(part, "text", None) or ""
                if t:
                    parts.append(t)
        ko = "".join(parts).strip()
    if not ko:
        return {"ok": False, "error": "translate_failed"}

    # WHY: 모델이 가끔 따옴표·접두를 붙임
    ko = ko.strip().strip("「」\"'")
    if ko.lower().startswith("korean:"):
        ko = ko.split(":", 1)[1].strip()

    with _LOCK:
        if len(_CACHE) >= _CACHE_MAX:
            # 단순 FIFO 근사: 절반 삭제
            for k in list(_CACHE.keys())[: _CACHE_MAX // 2]:
                _CACHE.pop(k, None)
        _CACHE[key] = ko

    return {"ok": True, "ko": ko, "cached": False}


def clear_translate_cache_for_tests() -> None:
    with _LOCK:
        _CACHE.clear()
