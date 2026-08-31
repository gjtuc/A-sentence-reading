"""
무엇을: debone 품질 가드 — coverage, grounding, chunk fallback (design/167).
왜: Gemini 청크 0문장이 조용히 통과하면 Experimental·Conclusion 등이 통째 소실된다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal

from sentence_reading.llm.richtext import plain_text, sanitize_sentence_html
from sentence_reading.models import Sentence

if TYPE_CHECKING:
    pass

CHUNK_SUBSTANTIVE_ALNUM = 120
CHUNK_SPARSE_ALNUM = 40
COVERAGE_LOW = 0.50
COVERAGE_WARN = 0.65
BODY_RATIO_WARN = 0.30
GROUNDING_MIN_WORDS = 5
GROUNDING_NGRAM = 5

REFERENCES_HEAD_RE = re.compile(
    r"^\s*(references|bibliography|acknowledg(e)?ments?)\b",
    re.IGNORECASE | re.MULTILINE,
)

_SECTION_ALIASES = {
    "intro": "introduction",
    "introduction": "introduction",
    "method": "methods",
    "methods": "methods",
    "experimental": "experimental",
    "experiment": "experimental",
    "result": "results",
    "results": "results",
    "discuss": "discussion",
    "discussion": "discussion",
    "conclusions": "conclusion",
    "conclusion": "conclusion",
    "summary": "conclusion",
    "title": "title",
    "abstract": "abstract",
    "body": "body",
    "supplementary": "supplementary",
}

ChunkKind = Literal["references", "substantive", "sparse"]


@dataclass
class ChunkStat:
    index: int
    chars_in: int
    sentences_out: int
    ok: bool
    kind: ChunkKind
    fallback: str | None = None


@dataclass
class IngestQuality:
    chunks_total: int = 0
    chunks_ok: int = 0
    chunks_failed: list[int] = field(default_factory=list)
    chunks_fallback_split: list[int] = field(default_factory=list)
    coverage_ratio: float = 1.0
    body_sentence_count: int = 0
    body_ratio: float = 0.0
    ungrounded_count: int = 0
    ungrounded_ids: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "chunks_total": self.chunks_total,
            "chunks_ok": self.chunks_ok,
            "chunks_failed": list(self.chunks_failed),
            "chunks_fallback_split": list(self.chunks_fallback_split),
            "coverage_ratio": round(self.coverage_ratio, 4),
            "body_sentence_count": self.body_sentence_count,
            "body_ratio": round(self.body_ratio, 4),
            "ungrounded_count": self.ungrounded_count,
            "ungrounded_ids": list(self.ungrounded_ids),
        }


def _alnum_count(text: str) -> int:
    return sum(1 for c in text if c.isalnum())


def chunk_kind(chunk: str) -> ChunkKind:
    alnum = _alnum_count(chunk)
    if alnum < CHUNK_SPARSE_ALNUM:
        return "sparse"
    head = chunk[:800]
    m = REFERENCES_HEAD_RE.search(head)
    if m:
        body_after = chunk[m.end() :]
        prose_lines = [
            ln
            for ln in body_after.splitlines()
            if len(re.findall(r"[a-zA-Z]{3,}", ln)) >= 3
        ]
        if len(prose_lines) < 2:
            return "references"
    if alnum >= CHUNK_SUBSTANTIVE_ALNUM:
        return "substantive"
    return "sparse"


def infer_section_for_chunk(idx: int, total: int, ctx: object) -> str:
    order = list(getattr(ctx, "section_order", None) or [])
    if not order:
        order = [
            "title",
            "abstract",
            "introduction",
            "methods",
            "results",
            "discussion",
            "conclusion",
        ]
    if total <= 1:
        return "body"
    center = (idx + 0.5) / total
    bucket = min(int(center * len(order)), len(order) - 1)
    key = order[bucket].strip().lower()
    return _SECTION_ALIASES.get(key, key if key in _SECTION_ALIASES.values() else "body")


def fallback_split_chunk(
    chunk: str,
    ctx: object,
    idx: int,
    total: int,
) -> list[tuple[str, str]]:
    from sentence_reading.pdf.sentences import split_into_sentences

    sec = infer_section_for_chunk(idx, total, ctx)
    rows = split_into_sentences(chunk)
    out: list[tuple[str, str]] = []
    for s in rows:
        piece = (s.text or "").strip()
        if not piece:
            continue
        plain = plain_text(piece)
        if len(plain) < 8:
            continue
        if len(plain) < 12 and re.fullmatch(r"[\d\-–,.\s]+", plain):
            continue
        out.append((sanitize_sentence_html(piece), sec))
    return out


def _token_set(text: str) -> set[str]:
    plain = plain_text(text).lower()
    return set(re.findall(r"[a-z0-9]{3,}", plain))


def compute_coverage_ratio(raw_text: str, sentences: list[Sentence]) -> float:
    raw_tok = _token_set(raw_text)
    if not raw_tok:
        return 1.0
    out_tok: set[str] = set()
    for s in sentences:
        out_tok |= _token_set(s.text)
    return len(raw_tok & out_tok) / len(raw_tok)


def check_sentence_grounded(text: str, raw_text: str) -> bool:
    plain = plain_text(text).lower()
    words = re.findall(r"[a-z0-9]+", plain)
    if len(words) < GROUNDING_MIN_WORDS:
        return True
    raw_norm = re.sub(r"\s+", " ", plain_text(raw_text).lower())
    n = GROUNDING_NGRAM
    for i in range(len(words) - n + 1):
        gram = " ".join(words[i : i + n])
        if gram in raw_norm:
            return True
    hits = 0
    for i in range(len(words) - 2):
        if " ".join(words[i : i + 3]) in raw_norm:
            hits += 1
    return hits >= 3


def apply_grounding_flags(
    sentences: list[Sentence], raw_text: str
) -> tuple[list[Sentence], list[str]]:
    ungrounded_ids: list[str] = []
    out: list[Sentence] = []
    for s in sentences:
        flags = tuple(s.quality_flags)
        if not check_sentence_grounded(s.text, raw_text):
            if "ungrounded" not in flags:
                flags = (*flags, "ungrounded")
            ungrounded_ids.append(s.id)
        out.append(
            Sentence(
                id=s.id,
                text=s.text,
                section=s.section,
                start_char=s.start_char,
                end_char=s.end_char,
                text_ko=s.text_ko,
                text_ko_stage=s.text_ko_stage,
                quality_flags=flags,
            )
        )
    return out, ungrounded_ids


def build_ingest_quality(
    *,
    raw_text: str,
    sentences: list[Sentence],
    chunk_stats: list[ChunkStat],
    ungrounded_ids: list[str],
    partial_debone_failed: list[int] | None = None,
) -> IngestQuality:
    n = len(chunk_stats)
    fallback = [s.index for s in chunk_stats if s.fallback == "split"]
    failed = list(partial_debone_failed or [])
    for s in chunk_stats:
        if s.kind == "substantive" and s.sentences_out == 0 and s.fallback != "split":
            if s.index not in failed:
                failed.append(s.index)
    chunks_ok = sum(
        1
        for s in chunk_stats
        if s.sentences_out > 0 or s.kind in ("references", "sparse")
    )
    body_count = sum(1 for s in sentences if (s.section or "body") == "body")
    total = max(len(sentences), 1)
    return IngestQuality(
        chunks_total=n,
        chunks_ok=chunks_ok,
        chunks_failed=failed,
        chunks_fallback_split=fallback,
        coverage_ratio=compute_coverage_ratio(raw_text, sentences),
        body_sentence_count=body_count,
        body_ratio=body_count / total,
        ungrounded_count=len(ungrounded_ids),
        ungrounded_ids=list(ungrounded_ids),
    )


def quality_to_warnings(
    iq: IngestQuality,
    *,
    survey_warnings: list[str] | None = None,
    missing_front_matter: bool = False,
) -> list[str]:
    w: list[str] = []
    for i in iq.chunks_fallback_split:
        w.append(f"chunk_fallback_split:{i}")
    if iq.chunks_failed or iq.chunks_ok < iq.chunks_total:
        w.append(f"partial_debone:{iq.chunks_ok}/{iq.chunks_total}")
    if missing_front_matter:
        w.append("missing_front_matter")
    if iq.coverage_ratio < COVERAGE_LOW:
        w.append(f"coverage_low:{iq.coverage_ratio:.2f}")
    elif iq.coverage_ratio < COVERAGE_WARN:
        w.append(f"coverage_warn:{iq.coverage_ratio:.2f}")
    if iq.body_ratio > BODY_RATIO_WARN:
        w.append(f"high_body_ratio:{iq.body_ratio:.2f}")
    if iq.ungrounded_count:
        w.append(f"ungrounded_sentences:{iq.ungrounded_count}")
    if survey_warnings:
        w.extend(survey_warnings)
    return list(dict.fromkeys(w))
