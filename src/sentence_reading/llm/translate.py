"""
무엇을: 학술 문장 영→한 번역 — 단순(35) + 다단계 draft/sense/polish(36).
왜: 한 방 번역의 용어·직역 흔들림을 역할 분리로 줄인다.
다음에: 용어집·중간 단계 UI·서버 prefs 동기화.
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
# WHY: 같은 문장 반복(←/→) 시 호출 절약 — 키에 mode 접두로 혼선 방지
_CACHE: dict[str, str] = {}
_CACHE_MAX = 256

_PIPELINE_VERSION = "v1"

_SYSTEM_DRAFT = """You translate academic English into natural Korean for a researcher reading one sentence at a time.
Output Korean only — no quotes, no English echo, no preamble.
Keep chemical formulas, symbols, and proper nouns accurate; you may keep Latin formulas as-is when clearer.
Do not add explanations or footnotes.
"""

_SYSTEM_SENSE = """You are a scientific terminology editor for Korean translations of academic English.
You receive the English source and a Korean draft. Improve accuracy of technical terms, catalysis/chemistry wording, and symbols.
Keep formulas, units, and proper nouns correct — do not invent facts.
Output Korean only — no quotes, no English echo, no preamble, no explanation of changes.
"""

_SYSTEM_POLISH = """You are a Korean style editor for researchers reading one academic sentence at a time.
You receive the English source and a Korean draft that is already terminology-checked.
Make the Korean natural and easy to read without changing meaning, numbers, formulas, or technical terms.
Output Korean only — no quotes, no English echo, no preamble.
"""


def _plain(text: str) -> str:
    t = re.sub(r"<[^>]+>", " ", text or "")
    t = re.sub(r"\s+", " ", t).strip()
    return t


def _cache_key(prefix: str, plain: str) -> str:
    return prefix + hashlib.sha256(plain.encode("utf-8")).hexdigest()


def _clean_ko(ko: str) -> str:
    # WHY: 모델이 가끔 따옴표·접두를 붙임
    ko = (ko or "").strip().strip("「」\"'")
    if ko.lower().startswith("korean:"):
        ko = ko.split(":", 1)[1].strip()
    return ko.strip()


def _response_text(response: Any) -> str:
    ko = (getattr(response, "text", None) or "").strip()
    if ko:
        return _clean_ko(ko)
    parts: list[str] = []
    for cand in getattr(response, "candidates", None) or []:
        content = getattr(cand, "content", None)
        for part in getattr(content, "parts", None) or []:
            if getattr(part, "thought", False):
                continue
            t = getattr(part, "text", None) or ""
            if t:
                parts.append(t)
    return _clean_ko("".join(parts))


def _gemini_generate(system: str, user: str) -> str | None:
    """한 번 호출. 키 없음·빈 응답은 None. 예외는 상위로."""
    if not gemini_api_key():
        return None
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=gemini_api_key())
    response = client.models.generate_content(
        model=gemini_model(),
        contents=user,
        config=types.GenerateContentConfig(
            system_instruction=system,
            temperature=0.2,
            max_output_tokens=2048,
        ),
    )
    try:
        from sentence_reading.llm.usage_meter import record_gemini_response

        record_gemini_response(user, response)
    except Exception:  # noqa: BLE001
        pass
    text = _response_text(response)
    return text or None


def _cache_get(key: str) -> str | None:
    with _LOCK:
        return _CACHE.get(key)


def _cache_put(key: str, ko: str) -> None:
    with _LOCK:
        if len(_CACHE) >= _CACHE_MAX:
            for k in list(_CACHE.keys())[: _CACHE_MAX // 2]:
                _CACHE.pop(k, None)
        _CACHE[key] = ko


def _validate_plain(text: str) -> tuple[str | None, dict[str, Any] | None]:
    plain = _plain(text)
    if not plain:
        return None, {"ok": False, "error": "empty"}
    if len(plain) > _MAX_CHARS:
        # WHY: 실수로 논문 전체·노트 덤프가 오면 비용·지연 폭발 방지
        return None, {"ok": False, "error": "too_long", "max_chars": _MAX_CHARS}
    return plain, None


def translate_en_to_ko(text: str) -> dict[str, Any]:
    """
    단순 1회 번역 (design/35).
    # INVARIANT: empty / too_long / no-key 는 Gemini 를 호출하지 않는다.
    """
    plain, err = _validate_plain(text)
    if err:
        return err
    assert plain is not None

    key = _cache_key("simple:", plain)
    hit = _cache_get(key)
    if hit is not None:
        return {"ok": True, "ko": hit, "cached": True, "mode": "simple", "stages_done": ["draft"]}

    if not gemini_api_key():
        return {"ok": False, "error": "gemini_unavailable"}

    ko = _gemini_generate(_SYSTEM_DRAFT, f"Translate to Korean:\n\n{plain}")
    if not ko:
        return {"ok": False, "error": "translate_failed"}

    _cache_put(key, ko)
    return {
        "ok": True,
        "ko": ko,
        "cached": False,
        "mode": "simple",
        "stages_done": ["draft"],
    }


def translate_en_to_ko_pipeline(text: str) -> dict[str, Any]:
    """
    draft → sense → polish (design/36).
    # INVARIANT: 후속 단계 실패 시 직전 ko 로 fail-soft 성공.
    """
    plain, err = _validate_plain(text)
    if err:
        return err
    assert plain is not None

    key = _cache_key(f"pipeline:{_PIPELINE_VERSION}:", plain)
    hit = _cache_get(key)
    if hit is not None:
        return {
            "ok": True,
            "ko": hit,
            "cached": True,
            "mode": "pipeline",
            "stages_done": ["draft", "sense", "polish"],
        }

    if not gemini_api_key():
        return {"ok": False, "error": "gemini_unavailable"}

    stages_done: list[str] = []
    draft = _gemini_generate(_SYSTEM_DRAFT, f"Translate to Korean:\n\n{plain}")
    if not draft:
        return {"ok": False, "error": "translate_failed"}
    stages_done.append("draft")
    current = draft

    try:
        sense = _gemini_generate(
            _SYSTEM_SENSE,
            f"English source:\n{plain}\n\nKorean draft:\n{current}\n\nRevise for terminology.",
        )
        if sense:
            current = sense
            stages_done.append("sense")
        else:
            log.warning("translate sense empty — keeping draft")
    except Exception as exc:  # noqa: BLE001
        log.warning("translate sense failed: %s", exc)

    try:
        polish = _gemini_generate(
            _SYSTEM_POLISH,
            f"English source:\n{plain}\n\nKorean draft:\n{current}\n\nPolish for readability.",
        )
        if polish:
            current = polish
            stages_done.append("polish")
        else:
            log.warning("translate polish empty — keeping prior stage")
    except Exception as exc:  # noqa: BLE001
        log.warning("translate polish failed: %s", exc)

    # WHY: 전체 pipeline 완료본만 캐시 — 부분 성공은 다음 시도에서 재도전
    if stages_done == ["draft", "sense", "polish"]:
        _cache_put(key, current)

    return {
        "ok": True,
        "ko": current,
        "cached": False,
        "mode": "pipeline",
        "stages_done": stages_done,
    }


def translate_dispatch(text: str, mode: str = "pipeline") -> dict[str, Any]:
    """API 진입점. mode 정규화."""
    m = (mode or "pipeline").strip().lower()
    if m not in ("pipeline", "simple"):
        return {"ok": False, "error": "invalid_mode"}
    if m == "simple":
        return translate_en_to_ko(text)
    return translate_en_to_ko_pipeline(text)


def clear_translate_cache_for_tests() -> None:
    with _LOCK:
        _CACHE.clear()
