"""
무엇을: TTS에 넘기기 전 말할 말로 정규화 (첨자·기호·구역 접두).
왜: plain_text 만 쓰면 H2O·cm−1·Title: 을 글자 그대로 읽어 어색하다.
다음에: 단위(cm−1→per centimeter) 사전 확장.
"""

from __future__ import annotations

import html as html_lib
import re
from html.parser import HTMLParser

_SECTION_PREFIX = re.compile(
    r"^\s*(Title|Abstract|Introduction|Methods|Experimental|Results|"
    r"Discussion|Conclusion|Body)\s*:\s*",
    re.IGNORECASE,
)

_DIGIT_WORD = {
    "0": "zero",
    "1": "one",
    "2": "two",
    "3": "three",
    "4": "four",
    "5": "five",
    "6": "six",
    "7": "seven",
    "8": "eight",
    "9": "nine",
}

# 표시용 기호 → 영어 발음 (논문 빈도 높은 것만)
_SYMBOL_SPOKEN = (
    ("≤", " less than or equal to "),
    ("≥", " greater than or equal to "),
    ("≠", " not equal to "),
    ("±", " plus or minus "),
    ("×", " times "),
    ("·", " times "),
    ("→", " goes to "),
    ("↔", " exchange "),
    ("∞", " infinity "),
    ("°C", " degrees Celsius "),
    ("°F", " degrees Fahrenheit "),
    ("Å", " angstrom "),
    ("µ", " micro "),
    ("μ", " mu "),
    ("α", " alpha "),
    ("β", " beta "),
    ("γ", " gamma "),
    ("δ", " delta "),
    ("Δ", " delta "),
    ("ε", " epsilon "),
    ("θ", " theta "),
    ("λ", " lambda "),
    ("π", " pi "),
    ("σ", " sigma "),
    ("τ", " tau "),
    ("φ", " phi "),
    ("ω", " omega "),
    ("Ω", " ohm "),
    ("−", " minus "),
    ("–", " "),
    ("—", " "),
)


def _speak_numberish(raw: str) -> str:
    """첨자/윗첨자 내용 → 짧게 말할 말."""
    s = (raw or "").strip()
    if not s:
        return ""
    s = (
        s.replace("−", "-")
        .replace("–", "-")
        .replace("—", "-")
        .replace("＋", "+")
    )
    # 순수 부호+숫자(+소수)
    m = re.fullmatch(r"([+\-]?)(\d+)(?:\.(\d+))?", s)
    if m:
        sign, whole, frac = m.group(1), m.group(2), m.group(3)
        parts: list[str] = []
        if sign == "-":
            parts.append("minus")
        elif sign == "+":
            parts.append("plus")
        if len(whole) == 1:
            parts.append(_DIGIT_WORD.get(whole, whole))
        elif whole == "10":
            parts.append("ten")
        else:
            parts.extend(_DIGIT_WORD.get(ch, ch) for ch in whole)
        if frac is not None:
            parts.append("point")
            parts.extend(_DIGIT_WORD.get(ch, ch) for ch in frac)
        return " ".join(parts)
    # 짧은 원소/기호: 글자 사이 공백
    if re.fullmatch(r"[A-Za-z]{1,4}", s):
        return " ".join(s)
    if len(s) <= 8 and re.fullmatch(r"[A-Za-z0-9+\-.,]+", s):
        out: list[str] = []
        for ch in s:
            if ch.isdigit():
                out.append(_DIGIT_WORD.get(ch, ch))
            elif ch == ".":
                out.append("point")
            elif ch == "-":
                out.append("minus")
            elif ch == "+":
                out.append("plus")
            else:
                out.append(ch)
        return " ".join(out)
    return s


class _ToSpoken(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._out: list[str] = []
        self._mode: list[str] = []  # "", "sub", "sup"

    def handle_starttag(self, tag: str, attrs) -> None:  # noqa: ANN001
        t = tag.lower()
        if t in ("sub", "sup"):
            self._mode.append(t)
        elif t in ("i", "em", "br"):
            if t == "br":
                self._out.append(" ")
        # 기타 태그 무시

    def handle_endtag(self, tag: str) -> None:
        t = tag.lower()
        if t in ("sub", "sup") and self._mode and self._mode[-1] == t:
            self._mode.pop()

    def handle_data(self, data: str) -> None:
        if not data:
            return
        mode = self._mode[-1] if self._mode else ""
        if mode == "sub":
            spoken = _speak_numberish(data)
            if spoken:
                self._out.append(f" {spoken} ")
        elif mode == "sup":
            spoken = _speak_numberish(data)
            if spoken:
                self._out.append(f" to the {spoken} ")
        else:
            self._out.append(data)

    def get_text(self) -> str:
        return "".join(self._out)


def _apply_symbols(text: str) -> str:
    s = text
    for raw, spoken in _SYMBOL_SPOKEN:
        if raw in s:
            s = s.replace(raw, spoken)
    return s


_UNI_SUB = str.maketrans("₀₁₂₃₄₅₆₇₈₉₊₋₌", "0123456789+-=")
_UNI_SUP = str.maketrans("⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻⁼", "0123456789+-=")


def _expand_unicode_scripts(text: str) -> str:
    """이미 유니코드 첨자인 경우 말로 풀기."""
    s = text

    def _sub_run(m: re.Match[str]) -> str:
        ascii_ = m.group(0).translate(_UNI_SUB)
        return f" {_speak_numberish(ascii_)} "

    def _sup_run(m: re.Match[str]) -> str:
        ascii_ = m.group(0).translate(_UNI_SUP)
        return f" to the {_speak_numberish(ascii_)} "

    s = re.sub(r"[₀₁₂₃₄₅₆₇₈₉₊₋₌]+", _sub_run, s)
    s = re.sub(r"[⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻⁼]+", _sup_run, s)
    return s


def _expand_plain_chem_digits(text: str) -> str:
    """
    태그 없이 온 H2O / CO2 / BaZr0.9 — 원소 뒤 숫자만 말로.
    WHY: debone 실패·폴백 문장 대비.
    """

    def _repl(m: re.Match[str]) -> str:
        el, num = m.group(1), m.group(2)
        return f"{el} {_speak_numberish(num)} "

    return re.sub(
        r"(?<![a-z])([A-Z][a-z]?)(\d+(?:\.\d+)?)",
        _repl,
        text,
    )


def spoken_text_for_tts(raw: str) -> str:
    """
    화면용 HTML/plain → TTS용 영어 말할 말.
    Title: 접두 제거 · sub/sup 풀어 읽기 · 흔한 기호 발음화.
    """
    s = (raw or "").strip()
    if not s:
        return ""

    # HTML 엔티티
    if "&" in s:
        s = html_lib.unescape(s)

    if "<" in s:
        parser = _ToSpoken()
        try:
            parser.feed(s)
            parser.close()
            s = parser.get_text()
        except Exception:  # noqa: BLE001
            s = re.sub(r"<[^>]+>", " ", s)

    # HTML 경로 후에도 남은 평문 첨자·화학식 숫자
    s = _expand_unicode_scripts(s)
    s = _expand_plain_chem_digits(s)

    s = _SECTION_PREFIX.sub("", s)
    s = _apply_symbols(s)
    s = re.sub(r"\s+", " ", s).strip()
    s = s.strip(" \t\"'`")
    return s
