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
# design/334 — a substantive chunk that returns less than this share of its prose
# has under-yielded, not succeeded. Deboning strips citation markers and running
# heads, so some shrinkage is normal; losing most of the chunk is not.
CHUNK_YIELD_MIN = 0.45
# design/335 — overruling a `references` pin needs the surviving prose to be most
# of the chunk. A reference list with a few stray lines is still a reference list,
# and those strays must not become practice sentences.
# Deleting body prose is the worse failure, so this floor only rejects a chunk
# that is overwhelmingly a reference list.
PIN_RESCUE_MIN_SHARE = 0.20
COVERAGE_LOW = 0.50
COVERAGE_WARN = 0.65
BODY_RATIO_WARN = 0.30
# design/321 — coverage against the pre-filter text. The extraction stage
# (section_flow drops, vision page replacement) is outside the debone denominator,
# so only this pair can tell "Gemini dropped it" from "extraction dropped it".
SOURCE_COVERAGE_LOW = 0.50
SOURCE_COVERAGE_WARN = 0.65
SOURCE_FILTER_GAP_WARN = 0.15
# design/333 — below this the denominator is too small to mean anything. Report
# nothing rather than a ratio computed over a handful of tokens.
COVERAGE_MIN_DENOM_TOKENS = 120
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
    # design/334 — characters the chunk actually returned. A chunk that gives
    # back a fraction of its prose used to report ok, because design/167 only
    # catches a chunk that returns nothing.
    chars_out: int = 0
    low_yield: bool = False
    # design/335 — characters this chunk dropped as bibliography, and whether an
    # upstream `references` pin was overruled because the text was prose.
    bib_chars_dropped: int = 0
    references_pin_rejected: bool = False

    @property
    def yield_ratio(self) -> float:
        if self.chars_in <= 0:
            return 1.0
        return self.chars_out / self.chars_in


@dataclass
class IngestQuality:
    chunks_total: int = 0
    chunks_ok: int = 0
    chunks_failed: list[int] = field(default_factory=list)
    chunks_fallback_split: list[int] = field(default_factory=list)
    # design/334 — chunks that came back with a fraction of their prose.
    chunks_low_yield: list[int] = field(default_factory=list)
    # design/335 — bibliography deletion, reported instead of assumed.
    bib_chars_dropped: int = 0
    references_pin_rejected: list[int] = field(default_factory=list)
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
            "chunks_low_yield": list(self.chunks_low_yield),
            "bib_chars_dropped": self.bib_chars_dropped,
            "references_pin_rejected": list(self.references_pin_rejected),
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
        # design/263 — EndNote-dense SI has many prose-like bib lines; trust parser.
        try:
            from sentence_reading.cite_refs import extract_bibliography

            if len(extract_bibliography(chunk)) >= 2:
                return "references"
        except Exception:  # noqa: BLE001
            pass
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


# design/333 — PDF extraction fuses a citation superscript onto the word before
# it (`coagulation16`, `study34`). Emitting the word as well as the fused token,
# on both sides of the comparison, lets the real word match.
_FUSED_CITE = re.compile(r"^([a-z]{5,})\d{1,3}$")


def _token_set(text: str) -> set[str]:
    plain = plain_text(text).lower()
    out = set(re.findall(r"[a-z0-9]{3,}", plain))
    for tok in list(out):
        m = _FUSED_CITE.match(tok)
        if m:
            out.add(m.group(1))
    return out


# design/333 — back matter and legal boilerplate a reader never says aloud. The
# per-page footer repeats on every page, so it dominates the token count.
_BACK_MATTER = re.compile(
    r"(?im)^\s*(?:"
    r"how to cite this article"
    r"|competing (?:financial )?interests?"
    r"|conflicts? of interest"
    r"|author contributions?"
    r"|additional information"
    r"|publisher'?s note"
    r"|data availability"
    r"|supplementary information"
    r"|this work is licensed under"
    r")\b"
)
_CHROME_LINE = re.compile(
    r"(?im)^.*(?:"
    r"creative ?commons"
    r"|www\.[a-z0-9.\-]+"
    r"|https?://"
    r"|doi:\s*10\."
    r"|\ball rights reserved\b"
    r"|\u00a9\s*(?:the author|\d{4})"
    r").*$"
)


def strip_back_matter(text: str) -> str:
    """design/333 — drop per-page chrome, then cut a late back-matter heading.

    A page footer such as `SCIENTIFIC REPORTS | 7:41797 | DOI: ... www.nature.com`
    repeats once per page, so on a short paper it can outweigh real prose in the
    recall denominator and make correct exclusion read as loss.

    The heading cut only fires in the **last third** of the text. A file holding
    more than one article carries another paper's `Supporting Online Material`
    near the top, and cutting there removed the target paper entirely: the Science
    excerpt's denominator collapsed to 9 tokens.
    """
    s = _CHROME_LINE.sub("", text or "")
    if not s.strip():
        return s
    floor = int(len(s) * 0.66)
    for m in _BACK_MATTER.finditer(s):
        if m.start() >= floor:
            return s[: m.start()]
    return s


def practice_text_only(raw_text: str) -> str:
    """design/330 — the part of the paper that is supposed to become sentences.

    A reference list is deliberately never practice text (design/263), so leaving
    it in the coverage denominator makes correct behaviour look like loss. On one
    Sci Rep paper the bibliography was 23,090 of 45,968 extracted characters, and
    coverage read 0.44 while almost nothing of the body was actually missing.

    Reuses the bibliography cut the SI path already trusts, which is a no-op when
    no bibliography parses, so a paper with an unusual back matter is unaffected.
    design/333 also removes back matter and per-page chrome.
    """
    from sentence_reading.cite_refs import cut_bibliography_for_sentences

    try:
        cut = cut_bibliography_for_sentences(raw_text or "")
    except Exception:  # noqa: BLE001
        cut = raw_text or ""
    return strip_back_matter(cut)


def coverage_excluding_references(
    raw_text: str,
    sentences: list[Sentence],
    *,
    references_text: str = "",
) -> float:
    """Recall against the practice text, not against the whole file.

    design/331 — `references_text` is the bibliography as `order_boxes` isolated
    it. It is not a substring of the raw column-interleaved text, so it is removed
    by **token set** rather than by slicing. That makes the denominator right on
    the Azure path even when `extract_bibliography` cannot find a header in the
    raw text.
    """
    _ = references_text  # design/333 — no longer subtracted; see the note below.
    raw_tok = _token_set(practice_text_only(raw_text))
    if not raw_tok:
        return 1.0
    out_tok: set[str] = set()
    for s in sentences:
        out_tok |= _token_set(s.text or "")
    return round(len(raw_tok & out_tok) / len(raw_tok), 4)


def practice_token_n(raw_text: str, references_text: str = "") -> int:
    """Size of the denominator design/330 reports on the handoff.

    design/333 — subtracting Azure's reference **tokens** is unsound. A reference
    title carries the paper's own topic words, so removing those tokens strips the
    body vocabulary with them: on `srep41797`, whose bibliography is 23,090 of
    50,975 characters, the denominator collapsed from ~600 tokens to 40 and the
    ratio became meaningless. The bibliography is removed by cutting the **text**
    (`practice_text_only`); `references_text` is kept for reporting only.
    """
    _ = references_text
    return len(_token_set(practice_text_only(raw_text)))


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
        chunks_low_yield=[s.index for s in chunk_stats if s.low_yield],
        bib_chars_dropped=sum(s.bib_chars_dropped for s in chunk_stats),
        references_pin_rejected=[
            s.index for s in chunk_stats if s.references_pin_rejected
        ],
        # design/330 — the bibliography is never practice text, so it must not
        # sit in the denominator and read as loss.
        coverage_ratio=coverage_excluding_references(raw_text, sentences),
        body_sentence_count=body_count,
        body_ratio=body_count / total,
        ungrounded_count=len(ungrounded_ids),
        ungrounded_ids=list(ungrounded_ids),
    )


def prose_chars(text: str) -> int:
    """Letters and digits only, so whitespace and markup do not skew the ratio."""
    return len(re.findall(r"[^\W_]", plain_text(text or ""), flags=re.UNICODE))


def pairs_chars(pairs: list[tuple[str, str]] | None) -> int:
    return sum(prose_chars(t) for t, _sec in (pairs or []))


def pin_rescue_worth_keeping(kept: str, original: str) -> bool:
    """design/335 — is what survived the bibliography filter really body prose?"""
    if chunk_kind(kept) != "substantive":
        return False
    whole = prose_chars(original)
    if whole <= 0:
        return False
    return (prose_chars(kept) / whole) >= PIN_RESCUE_MIN_SHARE


def chunk_under_yielded(chunk_text: str, pairs: list[tuple[str, str]] | None) -> bool:
    """design/334 — did this chunk hand back only a fraction of its prose?"""
    have = prose_chars(chunk_text)
    if have <= 0:
        return False
    return (pairs_chars(pairs) / have) < CHUNK_YIELD_MIN


def quality_to_warnings(
    iq: IngestQuality,
    *,
    survey_warnings: list[str] | None = None,
    missing_front_matter: bool = False,
) -> list[str]:
    w: list[str] = []
    for i in iq.chunks_fallback_split:
        w.append(f"chunk_fallback_split:{i}")
    for i in iq.chunks_low_yield:
        w.append(f"chunk_low_yield:{i}")
    for i in iq.references_pin_rejected:
        w.append(f"references_pin_rejected:{i}")
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


_ORDER_ANCHOR_NGRAM = 6
_ORDER_MIN_TOKENS = 5
ORDER_BACKWARD_PCT_WARN = 20.0


def _order_norm(text: str) -> str:
    s = re.sub(r"<[^>]+>", " ", text or "").lower()
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def _anchor_pos(sentence_norm: str, source_norm: str) -> int:
    toks = sentence_norm.split()
    if len(toks) < _ORDER_MIN_TOKENS:
        return -1
    span = min(_ORDER_ANCHOR_NGRAM, len(toks))
    for start in range(0, max(1, len(toks) - span + 1)):
        gram = " ".join(toks[start : start + span])
        if len(gram) < 12:
            continue
        at = source_norm.find(gram)
        if at >= 0:
            return at
    return -1


def source_order_stats(
    raw_text: str, sentences: list[Sentence]
) -> dict[str, float | int]:
    """design/322 — how often the stored order steps back in the source.

    One sentence is on screen at a time, so a reordering cannot be seen. This
    anchors each sentence in the source and counts backward steps. Sentences
    that cannot be anchored are excluded rather than guessed.
    """
    source_norm = _order_norm(raw_text)
    if not source_norm or not sentences:
        return {"anchored_n": 0, "backward_n": 0, "backward_pct": 0.0}
    positions: list[int] = []
    for s in sentences:
        at = _anchor_pos(_order_norm(getattr(s, "text", "") or ""), source_norm)
        if at >= 0:
            positions.append(at)
    if not positions:
        return {"anchored_n": 0, "backward_n": 0, "backward_pct": 0.0}
    backward = 0
    high = -1
    for p in positions:
        if high >= 0 and p < high:
            backward += 1
        high = max(high, p)
    pct = round(100.0 * backward / len(positions), 2)
    return {
        "anchored_n": len(positions),
        "backward_n": backward,
        "backward_pct": pct,
    }


def order_warnings(stats: dict[str, float | int]) -> list[str]:
    """design/322 — name a scrambled reading order."""
    n = int(stats.get("anchored_n") or 0)
    if n < 20:
        return []
    pct = float(stats.get("backward_pct") or 0.0)
    if pct > ORDER_BACKWARD_PCT_WARN:
        return [f"sentence_order_backward:{pct:.1f}"]
    return []


def practice_text_for_coverage(raw: str) -> str:
    """design/330 — the part of the paper practice is supposed to cover.

    A reference list is deliberately not practice text (design/263), so counting
    it in the coverage denominator makes correct behaviour look like loss. On one
    real Sci Rep paper the bibliography was 23,090 of 45,968 extracted
    characters, and coverage read 0.437 while the body was almost fully covered.

    Reuses the SI cut, which is a no-op when no bibliography parses, so a paper
    whose references cannot be found keeps the old denominator rather than
    guessing a boundary.
    """
    from sentence_reading.cite_refs import cut_bibliography_for_sentences

    text = raw or ""
    try:
        cut = cut_bibliography_for_sentences(text)
    except Exception:  # noqa: BLE001
        return text
    # Refuse an implausible cut: a bibliography is back matter, not the paper.
    if not cut.strip() or len(cut) < len(text) * 0.25:
        return text
    return cut


def coverage_is_measurable(denom_tokens: int) -> bool:
    """design/333 — a ratio over a handful of tokens is not a measurement."""
    return int(denom_tokens or 0) >= COVERAGE_MIN_DENOM_TOKENS


def source_coverage_warnings(
    *,
    source_coverage: float,
    debone_coverage: float,
    denom_tokens: int | None = None,
) -> list[str]:
    """design/321 — recall against the pre-filter text, and the filter's share.

    `debone_coverage` is measured against the text debone was handed. When the
    source ratio is much lower, the loss happened before debone and no existing
    warning can see it.
    """
    w: list[str] = []
    if denom_tokens is not None and not coverage_is_measurable(denom_tokens):
        return [f"coverage_denom_too_small:{int(denom_tokens)}"]
    src = float(source_coverage)
    if src < SOURCE_COVERAGE_LOW:
        w.append(f"source_coverage_low:{src:.2f}")
    elif src < SOURCE_COVERAGE_WARN:
        w.append(f"source_coverage_warn:{src:.2f}")
    gap = float(debone_coverage) - src
    if debone_coverage > 0 and gap > SOURCE_FILTER_GAP_WARN:
        w.append(f"extract_filter_gap:{gap:.2f}")
    return list(dict.fromkeys(w))
