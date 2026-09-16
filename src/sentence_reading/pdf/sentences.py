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


_CAPTION_STUB = re.compile(
    r"^(?:Fig(?:ure)?|Scheme|Table)\.?\s*S?\d+[a-z]?\.?$",
    re.IGNORECASE,
)


def split_stub_stats(sentences: list[Sentence], *, splitter: str) -> dict[str, int | str]:
    """design/294 — caption-only cards after the ingest sentence split."""
    stub_n = 0
    for s in sentences:
        piece = re.sub(r"\s+", " ", (s.text or "").strip())
        if piece and _CAPTION_STUB.match(piece):
            stub_n += 1
    return {
        "splitter": splitter,
        "sentence_n": len(sentences),
        "stub_caption_n": stub_n,
    }


_LEADING_CAPTION = re.compile(
    r"^((?:Fig(?:ure)?|Scheme|Table)\.\s+S?\d+[a-z]?)\.(?=\s)",
    re.IGNORECASE,
)
_INITIAL = re.compile(r"^[A-Z]\.$")


def _merge_caption_paragraphs(text: str) -> list[str]:
    """Keep a lone 'Fig. S4.' paragraph with the caption that follows it."""
    blocks = [b.strip() for b in re.split(r"\n\s*\n", text.strip()) if b.strip()]
    merged: list[str] = []
    i = 0
    while i < len(blocks):
        cur = blocks[i]
        if _CAPTION_STUB.match(cur) and i + 1 < len(blocks):
            nxt = blocks[i + 1]
            if nxt and not _CAPTION_STUB.match(nxt):
                merged.append(f"{cur} {nxt}")
                i += 2
                continue
        merged.append(cur)
        i += 1
    return merged


def _protect_leading_caption(block: str) -> str:
    return _LEADING_CAPTION.sub(lambda m: m.group(1) + "\uE000", block, count=1)


def _merge_stub_segments(segments: list[str]) -> list[str]:
    out: list[str] = []
    i = 0
    while i < len(segments):
        cur = segments[i].strip()
        if i + 1 < len(segments) and (
            _CAPTION_STUB.match(cur) or _INITIAL.fullmatch(cur)
        ):
            nxt = segments[i + 1].strip()
            if nxt and not _CAPTION_STUB.match(nxt):
                out.append(f"{cur} {nxt}")
                i += 2
                continue
        if cur:
            out.append(cur)
        i += 1
    return out


def split_into_sentences_detailed(raw_text: str) -> tuple[list[Sentence], str]:
    """Same cards as split_into_sentences, plus which splitter ran (design/294)."""
    text = (raw_text or "").strip()
    if not text:
        return [], "empty"

    splitter = "heuristic"
    segments: list[str] = []
    for block in _merge_caption_paragraphs(text):
        protected = _protect_leading_caption(block)
        parts = _split_pysbd(protected)
        if parts is None:
            parts = _split_heuristic(protected)
        else:
            splitter = "pysbd"
        segments.extend(p.replace("\uE000", ".") for p in parts)
    segments = _merge_stub_segments(segments)
    return _sentences_from_segments(text, segments), splitter


def split_into_sentences(raw_text: str) -> list[Sentence]:
    """원문을 문장 단위로 나눈다. pysbd가 있으면 우선 사용."""
    sentences, _splitter = split_into_sentences_detailed(raw_text)
    return sentences


def _sentences_from_segments(text: str, segments: list[str]) -> list[Sentence]:

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
    # 약어·이름 이니셜 뒤 마침표는 임시 보호
    protected = re.sub(
        rf"\b({_ABBREV})\.",
        lambda m: m.group(0).replace(".", "\uE000"),
        text,
        flags=re.IGNORECASE,
    )
    protected = re.sub(
        r"\b([A-Z])\.(?=\s+[A-Z])",
        lambda m: m.group(1) + "\uE000",
        protected,
    )
    parts = re.split(r"(?<=[.!?])\s+(?=[A-Z\"'])", protected)
    return [p.replace("\uE000", ".") for p in parts if p.strip()]
