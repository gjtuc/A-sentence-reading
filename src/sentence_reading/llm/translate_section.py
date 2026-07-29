"""
무엇을: ingest 시 섹션 단위 영→한 (기존 pipeline + 요지 재감수 + 캡션).
왜: 문장 단독 live 번역보다 말투·용어·대기 개선 (design/40).
다음에: 용어집·부분 재번역 API.

흐름 (섹션마다):
  1) 문장별 translate_dispatch(pipeline)
  2) 섹션 EN 묶음 → digest(EN+KO)
  3) digest로 각 text_ko harmonize
  4) 그림 caption도 pipeline (+ body digest 재감수)

INVARIANT: 점수/채점 없음. 실패는 항목 단위 스킵(경고만).
NOTE: Live Enable / IPS 는 Trading Gate — ASR 밖.
"""

from __future__ import annotations

import logging
import re
from dataclasses import replace
from typing import Any

from sentence_reading.llm import translate as tr
from sentence_reading.llm.env import gemini_api_key
from sentence_reading.models import Figure, Sentence

log = logging.getLogger(__name__)

# WHY: rich-v* 와 분리 — 번역만 바뀌어도 PDF 재분석 강제하지 않음
TRANSLATE_DOC_VERSION = "doc-v1"


def needs_translate_backfill(
    sentences: list[Sentence],
    figures: list[Figure],
    digests: dict | None = None,
) -> bool:
    """
    보관본에 ingest 번역이 사실상 없으면 True.
    WHY: rich-v6 캐시 히트가 번역 stage를 건너뛰던 구멍 (design/42).
    """
    if digests and any(
        isinstance(v, dict)
        and (str(v.get("en") or "").strip() or str(v.get("ko") or "").strip())
        for v in digests.values()
    ):
        return False
    n = len(sentences or [])
    if n == 0:
        # 문장 없으면 번역할 것 없음 — 백필 불필요
        return False
    filled = sum(1 for s in sentences if (getattr(s, "text_ko", None) or "").strip())
    if filled / n >= 0.05:
        return False
    if any((getattr(f, "caption_ko", None) or "").strip() for f in (figures or [])):
        return False
    return True


_DIGEST_SYSTEM = """You summarize one academic paper section for a Korean researcher.
Return exactly two blocks:
EN: <2-4 English sentences: core claim and key terms>
KO: <2-4 Korean sentences: same content, natural academic Korean>
No other preamble. Keep formulas/symbols accurate.
"""

_HARMONIZE_SYSTEM = """You revise a Korean translation of one academic English sentence.
You are given the section's theme summary (EN+KO) and must make terminology and tone consistent with that theme.
Output Korean only — no quotes, no English echo, no preamble.
Do not invent facts; keep formulas and numbers.
"""


def _plain(text: str) -> str:
    """HTML/공백 정리 — 번역·digest 입력용. 빈 문자열이면 skip."""
    t = re.sub(r"<[^>]+>", " ", text or "")
    t = re.sub(r"\s+", " ", t).strip()
    return t


def _section_key(section: str | None) -> str:
    """빈/None section → body. UI 되새김질 키와 맞춤."""
    s = (section or "body").strip().lower() or "body"
    return s


def _parse_digest(raw: str) -> dict[str, str]:
    """
    EN:/KO: 블록 파싱.
    WHY: 모델이 형식을 살짝 깨도 관대하게 — 마커 없으면 전체를 KO로.
    """
    en, ko = "", ""
    if not raw:
        return {"en": "", "ko": ""}
    m_en = re.search(
        r"(?is)\bEN\s*:\s*(.*?)(?=\bKO\s*:|$)",
        raw,
    )
    m_ko = re.search(r"(?is)\bKO\s*:\s*(.*?)$", raw)
    if m_en:
        en = m_en.group(1).strip()
    if m_ko:
        ko = m_ko.group(1).strip()
    if not en and not ko:
        ko = raw.strip()
    return {"en": en, "ko": ko}


def _pipeline_one(text: str) -> str | None:
    """기존 design/36 pipeline 1회. 실패·빈 입력 → None (호출측이 skip)."""
    plain = _plain(text)
    if not plain:
        return None
    if len(plain) > tr._MAX_CHARS:
        # WHY: live /api/translate 와 동일 한도 — 잘라도 번역 시도
        plain = plain[: tr._MAX_CHARS]
    out = tr.translate_dispatch(plain, "pipeline")
    if not out.get("ok"):
        return None
    return str(out.get("ko") or "") or None


def _make_digest(section: str, english_lines: list[str]) -> dict[str, str]:
    """섹션 핵심 요지 (EN+KO). 키/문장 없으면 빈 digest."""
    if not gemini_api_key() or not english_lines:
        return {"en": "", "ko": ""}
    # WHY: 토큰 폭주 방지 — 섹션당 최대 40문장
    joined = "\n".join(f"- {t}" for t in english_lines[:40])
    user = (
        f"Section id: {section}\n"
        f"Sentences:\n{joined}\n\n"
        "Write EN: and KO: theme summaries."
    )
    try:
        raw = tr._gemini_generate(_DIGEST_SYSTEM, user)
    except Exception as exc:  # noqa: BLE001
        log.warning("digest failed %s: %s", section, exc)
        return {"en": "", "ko": ""}
    return _parse_digest(raw or "")


def _harmonize(en: str, ko: str, digest: dict[str, str]) -> str:
    """요지 기준으로 draft KO 재감수. 실패 시 원 draft 유지 (fail-soft)."""
    if not gemini_api_key() or not ko:
        return ko
    theme = (
        f"EN theme: {digest.get('en') or '(none)'}\n"
        f"KO theme: {digest.get('ko') or '(none)'}"
    )
    user = (
        f"{theme}\n\nEnglish source:\n{en}\n\nKorean draft:\n{ko}\n\n"
        "Revise Korean for theme consistency."
    )
    try:
        out = tr._gemini_generate(_HARMONIZE_SYSTEM, user)
    except Exception as exc:  # noqa: BLE001
        log.warning("harmonize failed: %s", exc)
        return ko
    return (out or ko).strip() or ko


def enrich_session_translations(
    sentences: list[Sentence],
    figures: list[Figure],
) -> tuple[list[Sentence], list[Figure], dict[str, dict[str, str]], list[str]]:
    """
    섹션별 pipeline → digest → harmonize.
    Gemini 없으면 입력 그대로 + warnings.
    # INVARIANT: score 없음. 실패 시 해당 항목만 스킵.
    """
    warnings: list[str] = []
    if not gemini_api_key():
        warnings.append("translate_skipped_no_gemini")
        return sentences, figures, {}, warnings

    by_sec: dict[str, list[int]] = {}
    for i, s in enumerate(sentences):
        by_sec.setdefault(_section_key(s.section), []).append(i)

    ko_map: dict[int, str] = {}
    digests: dict[str, dict[str, str]] = {}

    for sec, idxs in by_sec.items():
        # 1) pipeline per sentence
        for i in idxs:
            plain = _plain(sentences[i].text)
            if not plain:
                continue
            ko = _pipeline_one(plain)
            if ko:
                ko_map[i] = ko

        eng_lines = [
            _plain(sentences[i].text) for i in idxs if _plain(sentences[i].text)
        ]
        digest = _make_digest(sec, eng_lines)
        digests[sec] = digest

        # 2) harmonize with digest (요지 없으면 draft 유지)
        if digest.get("en") or digest.get("ko"):
            for i in idxs:
                if i not in ko_map:
                    continue
                ko_map[i] = _harmonize(
                    _plain(sentences[i].text),
                    ko_map[i],
                    digest,
                )

    # WHY: replace — Figure/Sentence 필드가 늘어도 복사 누락 방지
    new_sentences = [
        replace(s, text_ko=ko_map.get(i) or "") for i, s in enumerate(sentences)
    ]

    # 캡션: pipeline (+ body digest가 있으면 짧게 harmonize)
    body_digest = digests.get("body") or next(
        iter(digests.values()), {"en": "", "ko": ""}
    )
    new_figures: list[Figure] = []
    for fig in figures:
        cap = _plain(fig.caption)
        cap_ko = ""
        if cap:
            cap_ko = _pipeline_one(cap) or ""
            if cap_ko and (body_digest.get("en") or body_digest.get("ko")):
                cap_ko = _harmonize(cap, cap_ko, body_digest)
        new_figures.append(replace(fig, caption_ko=cap_ko or ""))

    if not any(s.text_ko for s in new_sentences) and not any(
        f.caption_ko for f in new_figures
    ):
        warnings.append("translate_empty")

    return new_sentences, new_figures, digests, warnings


def digest_public(digests: dict[str, Any] | None) -> dict[str, dict[str, str]]:
    """API/캐시용 — 이상한 값도 str로 정규화."""
    out: dict[str, dict[str, str]] = {}
    if not isinstance(digests, dict):
        return out
    for k, v in digests.items():
        if not isinstance(v, dict):
            continue
        out[str(k)] = {
            "en": str(v.get("en") or ""),
            "ko": str(v.get("ko") or ""),
        }
    return out
