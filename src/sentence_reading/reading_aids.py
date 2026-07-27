"""
무엇을: 표시용 영문 음절 경계(·) — Immersive Reader식 읽기 보조.
왜: crowding 완화 · TTS/원문 의미는 바꾸지 않음 (design/30).
엔진: pyphen en_US. 품사 색은 다음 턴.
"""

from __future__ import annotations

import re
from functools import lru_cache

_WORD = re.compile(r"[A-Za-z]+(?:'[A-Za-z]+)?")
_TAG_SPLIT = re.compile(r"(<[^>]+>)")


@lru_cache(maxsize=1)
def _dic():
    try:
        import pyphen
    except ImportError:
        return None
    try:
        return pyphen.Pyphen(lang="en_US")
    except Exception:
        return None


def syllabify_word(word: str) -> str:
    """한 단어 → mid-dot 음절. 사전 없거나 짧으면 그대로."""
    if len(word) < 4:
        return word
    dic = _dic()
    if dic is None:
        return word
    try:
        inserted = dic.inserted(word, hyphen="·")
    except Exception:
        return word
    if not inserted or "·" not in inserted:
        return word
    return inserted


def syllabify_plain(text: str) -> str:
    if not text:
        return ""

    def repl(m: re.Match[str]) -> str:
        return syllabify_word(m.group(0))

    return _WORD.sub(repl, text)


def syllabify_html(html: str) -> str:
    """태그 밖 텍스트만 음절화."""
    if not html:
        return ""
    if "<" not in html:
        return syllabify_plain(html)
    parts: list[str] = []
    for chunk in _TAG_SPLIT.split(html):
        if chunk.startswith("<") and chunk.endswith(">"):
            parts.append(chunk)
        else:
            parts.append(syllabify_plain(chunk))
    return "".join(parts)


def apply_reading_aids(text: str, *, syllables: bool = False) -> str:
    out = text or ""
    if syllables:
        out = syllabify_html(out)
    return out
