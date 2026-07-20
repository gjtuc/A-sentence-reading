"""
무엇을: 원문 문자열 → Sentence 리스트.
왜: UI 단위는 페이지/단락이 아니라 **한 문장**이다.
다음에: pysbd 기본 + 약어 픽스처 강화.
"""

from __future__ import annotations

import re

from sentence_reading.models import Sentence

# WHY: `\\. ` 만 쓰면 Fig. / et al. / i.e. 에서 잘못 끊김 (docs/design/03)
_ABBREV = (
    r"Fig|Figs|Eq|Eqs|Ref|Refs|Vol|No|Nos|Dr|Mr|Mrs|Ms|Prof|vs|cf|al|"
    r"e\.g|i\.e|et al|approx|ca|ed|eds|pp"
)


def split_into_sentences(raw_text: str) -> list[Sentence]:
    """원문을 문장 단위로 나눈다. pysbd가 있으면 우선 사용."""
    text = (raw_text or "").strip()
    if not text:
        return []

    segments = _split_pysbd(text)
    if segments is None:
        segments = _split_heuristic(text)

    sentences: list[Sentence] = []
    search_from = 0
    for i, seg in enumerate(segments):
        piece = seg.strip()
        if not piece:
            continue
        start = text.find(piece, search_from)
        end = start + len(piece) if start >= 0 else None
        if start >= 0:
            search_from = end or search_from
        sentences.append(
            Sentence(
                id=f"sent_{i:06d}",
                text=piece,
                start_char=start if start >= 0 else None,
                end_char=end,
            )
        )
        if len(sentences) >= 5000:
            break
    return sentences


def _split_pysbd(text: str) -> list[str] | None:
    try:
        import pysbd
    except ImportError:
        return None
    seg = pysbd.Segmenter(language="en", clean=False)
    return list(seg.segment(text))


def _split_heuristic(text: str) -> list[str]:
    # 약어 뒤 마침표는 임시 보호
    protected = re.sub(
        rf"\b({_ABBREV})\.",
        lambda m: m.group(0).replace(".", "\uE000"),
        text,
        flags=re.IGNORECASE,
    )
    parts = re.split(r"(?<=[.!?])\s+(?=[A-Z\"'])", protected)
    return [p.replace("\uE000", ".") for p in parts if p.strip()]
