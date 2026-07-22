"""
무엇을: survey 화학식 용어집 적용 + PDF 추출 과학 기호 정규화.
왜: Gemini가 <sub>를 빠뜨리거나, PDF ToUnicode이 ◦/µ 등을 잘못 매핑한다 (design/13).
다음에: PDF span 좌표 기반 첨자.
"""

from __future__ import annotations

import re

from sentence_reading.llm.richtext import sanitize_sentence_html

# 캐시 무효화 — 이 값이 다르면 ingest가 보관본을 건너뛰고 다시 다듬음
PIPELINE_VERSION = "rich-v2"

# PDF가 도(°) 대신 자주 내보내는 원형 lookalike
# U+25E6 ◦ white bullet, U+2218 ∘ ring operator, U+02DA ˚ ring above,
# U+00BA º masculine ordinal, U+00B0 ° degree (간격 정리용으로 포함)
_DEGREE_LOOKALIKE = r"[◦∘˚º°\u00BA\u02DA\u2218\u25E6\u00B0]"


def _dash_variants(s: str) -> list[str]:
    out = {s}
    for a, b in (
        ("-", "−"),
        ("−", "-"),
        ("-", "–"),
        ("–", "-"),
        ("δ", "𝛿"),
        ("𝛿", "δ"),
    ):
        if a in s:
            out.add(s.replace(a, b))
    return sorted(out, key=len, reverse=True)


def _safe_symbol_raw(raw: str) -> bool:
    """한 글자 라틴(x, T…)은 단어 파괴 → 제외. 그리스·2글자+만."""
    raw = (raw or "").strip()
    if len(raw) >= 2:
        return True
    if len(raw) != 1:
        return False
    o = ord(raw)
    return (0x0370 <= o <= 0x03FF) or (0x1F00 <= o <= 0x1FFF)


def _replace_outside_tags(text: str, raw: str, rich: str) -> str:
    """태그 밖 텍스트에만 raw→rich (중첩 <i> inside <sub> 방지)."""
    if raw not in text:
        return text
    parts = re.split(r"(<[^>]+>)", text)
    out: list[str] = []
    for part in parts:
        if part.startswith("<") and part.endswith(">"):
            out.append(part)
        else:
            out.append(part.replace(raw, rich))
    return "".join(out)


def _map_plain_segments(text: str, fn) -> str:  # noqa: ANN001
    """HTML 태그 밖 조각에만 fn 적용."""
    if "<" not in text:
        return fn(text)
    parts = re.split(r"(<[^>]+>)", text)
    return "".join(
        part if part.startswith("<") and part.endswith(">") else fn(part) for part in parts
    )


def normalize_scientific_glyphs(text: str) -> str:
    """
    PDF 추출 lookalike → 표준 과학 표기.
    참고: poppler-science(µ↔m), Adobe µ/μ, TeX ToUnicode 깨짐 등.
    """
    if not text:
        return ""

    def _fix(seg: str) -> str:
        s = seg
        # PDF soft hyphen (줄바꿈 하이픈) 제거
        s = s.replace("\u00ad", "")

        # 섭씨/화씨: 1650 ◦C, 1000˚C, ºC → °C (도 기호 U+00B0; <sup> 불필요)
        s = re.sub(rf"{_DEGREE_LOOKALIKE}\s*([CF])\b", r"°\1", s)
        # 각도 등: 90◦, 0.02◦ → 90°, 0.02°
        s = re.sub(rf"(?<=\d)\s*{_DEGREE_LOOKALIKE}(?=[A-Za-z])", "° ", s)
        s = re.sub(rf"(?<=\d)\s*{_DEGREE_LOOKALIKE}", "°", s)
        # 숫자와 도 사이 공백: 1000 °C 유지, 1000° C → 1000°C
        s = re.sub(r"(\d)\s*°\s*([CF])\b", r"\1°\2", s)

        # 옹스트롬 (드묾)
        s = re.sub(r"\bA\s*(?:˚|°|º)\b", "Å", s)

        # 마이크로 단위: 그리스 μ / MICRO SIGN → MICRO SIGN(µ) + SI
        # WHY: µM vs mM 혼동 방지용으로 단위 접두만 통일 (변수 μ는 Gemini 이탤릭)
        s = re.sub(
            r"[μµ]\s*(m|A|V|W|g|L|l|mol|M|s|F|H|rad|bar)\b",
            r"µ\1",
            s,
        )

        # 플러스마이너스
        s = s.replace("+/-", "±").replace("+/−", "±").replace("+−", "±")

        # 곱셈 기호 (숫자 x 10^n 패턴만 — 단어 x 제외)
        s = re.sub(r"(\d)\s*[x×]\s*(10)\b", r"\1 × \2", s)

        return s

    return _map_plain_segments(text, _fix)


def apply_glossary(
    text: str,
    *,
    formulas: list[dict[str, str]] | None = None,
    symbols: list[dict[str, str]] | None = None,
) -> str:
    """기호 정규화 + 화학식 raw→rich 치환 후 sanitize.

    symbols는 한 글자(δ, x…)가 화학식·단어를 깨기 쉬워 **적용하지 않음**.
    (이탤릭은 Gemini 청크 출력에 맡김.)
    """
    out = normalize_scientific_glyphs(text or "")
    if not out:
        return ""
    _ = symbols  # API 호환 — 의도적으로 미사용

    items: list[tuple[str, str]] = []
    for row in formulas or []:
        raw = str(row.get("raw") or "").strip()
        rich = str(row.get("rich") or "").strip()
        if raw and rich and raw != rich:
            for v in _dash_variants(raw):
                items.append((v, rich))
    items.sort(key=lambda t: len(t[0]), reverse=True)

    for raw, rich in items:
        if rich not in out:
            out = _replace_outside_tags(out, raw, rich)

    return sanitize_sentence_html(out)
