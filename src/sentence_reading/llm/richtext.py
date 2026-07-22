"""
무엇을: 문장 rich HTML 허용 태그 sanitize · plain 추출.
왜: Gemini 출력을 그대로 innerHTML 하면 XSS·깨진 마크업 위험.
다음에: 수식(MathML) 필요 시 별도 경로.
"""

from __future__ import annotations

import html
import re
from html.parser import HTMLParser

# WHY: design/13 — sub/sup/italic only; no attributes
_ALLOWED = frozenset({"sub", "sup", "i", "em"})
_TAG_RE = re.compile(r"</?([a-zA-Z0-9]+)(?:\s[^>]*)?>")


class _StripToAllowed(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._out: list[str] = []
        self._stack: list[str] = []

    def handle_starttag(self, tag: str, attrs) -> None:  # noqa: ANN001
        t = tag.lower()
        if t in _ALLOWED:
            self._stack.append(t)
            self._out.append(f"<{t}>")

    def handle_endtag(self, tag: str) -> None:
        t = tag.lower()
        if t in _ALLOWED and self._stack and self._stack[-1] == t:
            self._stack.pop()
            self._out.append(f"</{t}>")

    def handle_data(self, data: str) -> None:
        self._out.append(html.escape(data, quote=False))

    def handle_entityref(self, name: str) -> None:
        self._out.append(f"&{name};")

    def handle_charref(self, name: str) -> None:
        self._out.append(f"&#{name};")

    def get_html(self) -> str:
        while self._stack:
            t = self._stack.pop()
            self._out.append(f"</{t}>")
        return "".join(self._out)


def plain_text(s: str) -> str:
    """태그 제거 후 표시용 plain."""
    if not s:
        return ""
    if "<" not in s:
        return s.strip()
    parser = _StripToAllowed()
    try:
        parser.feed(s)
        parser.close()
    except Exception:  # noqa: BLE001
        return _TAG_RE.sub("", s).strip()
    # re-parse as text only
    inner = parser.get_html()
    return re.sub(r"<[^>]+>", "", inner).strip()


def sanitize_sentence_html(s: str) -> str:
    """
    허용 태그만 남긴 HTML 조각.
    태그가 과다하거나 파싱 실패 시 plain으로 폴백.
    """
    raw = (s or "").strip()
    if not raw:
        return ""
    if "<" not in raw:
        return html.escape(raw, quote=False)

    parser = _StripToAllowed()
    try:
        parser.feed(raw)
        parser.close()
        out = parser.get_html().strip()
    except Exception:  # noqa: BLE001
        return html.escape(_TAG_RE.sub("", raw), quote=False).strip()

    if not out:
        return ""

    # WHY: 모델이 문장 전체를 <i>로 감싸는 남용 방지 — 태그 비율 높으면 plain
    plain = re.sub(r"<[^>]+>", "", out)
    tag_chars = len(out) - len(plain)
    if plain and tag_chars > max(80, len(plain) * 2):
        return html.escape(plain, quote=False).strip()

    return out
