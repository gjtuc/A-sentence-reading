"""
무엇을: debone 품질 가드 — coverage, grounding, chunk fallback (design/167).
왜: Gemini 청크 0문장이 조용히 통과하면 Experimental·Conclusion 등이 통째 소실된다.
"""

from __future__ import annotations

import re
from collections import Counter
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
# Reference-list signals per 1000 characters. Placed from the 32 pinned chunks of
# the 10-paper audit: the highest true-body region scores 1.94, the lowest true
# reference region 6.11, and nothing falls in between. 3.5 is the geometric middle
# of that gap, so the margin is 1.8x below and 1.75x above. 2.0 decided the same 32
# chunks but left only 3% of headroom under it.
REF_SIGNAL_DENSITY_MAX = 3.5
# design/336 — above this the bibliography deletion is worth naming. Measured
# bibliographies in the 10-paper audit run 467 to 18,398 characters, so this is
# not a rare-event threshold; it exists so the number is never silent.
BIB_DROPPED_REPORT_CHARS = 400
# A bibliography is back matter, not the paper. A cut that leaves less than this
# share of the text found the wrong boundary.
PRACTICE_CUT_MIN_SHARE = 0.25
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
    # design/345 — share of this chunk's prose that came back, reported only.
    text_coverage: float = 1.0
    # design/335 — characters this chunk dropped as bibliography, and whether a
    # `references` verdict was overruled because the text was prose.
    bib_chars_dropped: int = 0
    references_pin_rejected: bool = False
    # design/336 — which signal called this chunk a reference list: the section
    # pin, or `chunk_kind`'s own reading of the text.
    references_verdict: str = ""

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
    # design/336 — the same overrule, when `chunk_kind` was the one deleting.
    references_kind_rejected: list[int] = field(default_factory=list)
    # design/340 — journal apparatus kept out of practice, counted not assumed.
    back_matter_dropped: int = 0
    coverage_ratio: float = 1.0
    # design/344 — the text ruler. `coverage_ratio` compares word *lists*, so a lost
    # paragraph moves it by a fraction of a point. These two say how much of the
    # source text arrived and how many prose fragments did not.
    text_coverage: float = 1.0
    text_missing_n: int = 0
    # design/345 — glyph corruption that reached the reader, per 1000 characters.
    glyph_corruption_per_1k: float = 0.0
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
            "references_kind_rejected": list(self.references_kind_rejected),
            "back_matter_dropped": self.back_matter_dropped,
            "coverage_ratio": round(self.coverage_ratio, 4),
            "text_coverage": round(self.text_coverage, 4),
            "text_missing_n": self.text_missing_n,
            "glyph_corruption_per_1k": round(self.glyph_corruption_per_1k, 3),
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
    # design/340 — shapes the ten-paper corpus actually produced as practice
    # sentences.
    r"|supplementary (?:information|materials?|data)"
    r"|supporting (?:information|online material)"
    r"|open access article"
    r"|reprints? and permissions?"
    r"|author information"
    # design/341 — an RSC page stamp: `Downloaded on 5/28/2026 1:22:30 AM.`
    r"|downloaded (?:on|from)"
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


def is_back_matter_sentence(text: str) -> bool:
    """design/340 — is this sentence the journal's apparatus rather than the paper?

    `strip_back_matter` already removes exactly this text from the **coverage
    denominator**, so the metric called it "not practice text" while the product
    handed it to the reader to say aloud: licence blocks, `How to cite this
    article`, DOI lines, journal mastheads, `Supporting Online Material` plus its
    URL.

    Judged on the sentence's own evidence, not on a section label — a label can be
    wrong (design/335), and this decision removes content.

    Measured over 2,366 corpus sentences: 16 match, and every one is apparatus.
    """
    plain = plain_text(text or "").strip()
    if not plain:
        return False
    return bool(_CHROME_LINE.search(plain) or _BACK_MATTER.search(plain))


def drop_back_matter_sentences(
    sentences: list[Sentence],
) -> tuple[list[Sentence], int]:
    """Returns the kept sentences and how many were apparatus (design/340)."""
    kept = [s for s in sentences or [] if not is_back_matter_sentence(s.text or "")]
    return kept, len(sentences or []) - len(kept)


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

    design/336 — the implausible-cut refusal below used to live only in
    `practice_text_for_coverage`, which had no callers, so the live denominator ran
    unguarded. `bibliography_header_start` returns the *first* match with no
    position floor, so an SI cover sheet or a "see References therein" near the top
    could cut the paper away and make a 60% loss read as a measurement problem.
    """
    from sentence_reading.cite_refs import cut_bibliography_for_sentences

    text = raw_text or ""
    try:
        cut = cut_bibliography_for_sentences(text)
    except Exception:  # noqa: BLE001
        cut = text
    if not cut.strip() or len(cut) < len(text) * PRACTICE_CUT_MIN_SHARE:
        cut = text
    return strip_back_matter(cut)


# design/344 — the text ruler. A word-list metric cannot see a lost paragraph: on one
# real paper, deleting a 158-character sentence moved it by 0.12 points, because every
# word in that sentence also appeared somewhere else. So loss was measured with an
# instrument blind to the scale of loss that matters.
TEXT_FRAGMENT_MIN_WORDS = 6
TEXT_SHINGLE = 5
TEXT_FRAGMENT_FOUND_SHARE = 0.5
TEXT_COVERAGE_WARN = 0.80
_FRAGMENT_SPLIT = re.compile(r"(?<=[.!?])\s+|\n+")


def _shingles(words: list[str], n: int = TEXT_SHINGLE) -> set[tuple[str, ...]]:
    if len(words) < n:
        return {tuple(words)} if words else set()
    return {tuple(words[i : i + n]) for i in range(len(words) - n + 1)}


def _coverage_words(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", plain_text(text or "").lower())


def text_fragments(raw_text: str) -> list[str]:
    """Sentence-sized pieces of the source, long enough to be worth checking."""
    out: list[str] = []
    for piece in _FRAGMENT_SPLIT.split(practice_text_only(raw_text or "")):
        p = piece.strip()
        if len(_coverage_words(p)) >= TEXT_FRAGMENT_MIN_WORDS:
            out.append(p)
    return out


def text_coverage(
    raw_text: str, sentences: list[Sentence]
) -> tuple[float, list[str]]:
    """design/344 — which *pieces of text* reached the reader, not which words.

    A fragment counts as delivered when half of its 5-word shingles appear in the
    practice sentences. Half, not all: deboning legitimately removes citation
    markers and running heads, and a fragment can be split across two sentences.

    Returns the share of source characters delivered and the fragments that were not.
    A returned fragment is prose the reader should have had: mastheads, author lists
    and page stamps are dropped, or the list would be mostly noise.
    """
    frags = text_fragments(raw_text)
    if not frags:
        return 1.0, []
    out_words = _coverage_words(" ".join(s.text or "" for s in sentences or []))
    have = _shingles(out_words)
    missing: list[str] = []
    ok_chars = 0
    all_chars = 0
    for frag in frags:
        n = len(frag)
        all_chars += n
        want = _shingles(_coverage_words(frag))
        if not want:
            ok_chars += n
            continue
        share = len(want & have) / len(want)
        if share >= TEXT_FRAGMENT_FOUND_SHARE:
            ok_chars += n
        elif _delivered_reworded(frag, sentences):
            ok_chars += n
        elif _worth_reporting_missing(frag):
            missing.append(frag)
    return (round(ok_chars / max(all_chars, 1), 4), missing)


# design/347 — a second look before calling a fragment missing. Shingles cannot
# survive the system prompt's own instruction to prefer the glossary's rich form, so
# `covered with BZY10-1 wt% BaCO3` comes back as
# `covered with BaZr<sub>0.9</sub>Y<sub>0.1</sub>O<sub>3-δ</sub>-1 wt%` and every
# five-word window around it changes. Opened by hand, the sentence was there. Across
# the stored traces the shingle ruler alone was wrong about 18 of 33 fragments.
# Word overlap ignores order and so survives a rewritten token.
TEXT_REWORDED_SHARE = 0.70


def _delivered_reworded(fragment: str, sentences: list[Sentence] | None) -> bool:
    want = Counter(_coverage_words(fragment))
    if not want:
        return True
    total = sum(want.values())
    for s in sentences or []:
        have = Counter(_coverage_words(s.text or ""))
        hit = sum(min(k, have.get(w, 0)) for w, k in want.items())
        if hit / total >= TEXT_REWORDED_SHARE:
            return True
    return False


def _worth_reporting_missing(fragment: str) -> bool:
    """Is this fragment prose the reader should have had? (design/344)

    The first run of the text ruler returned mastheads, author name lists and RSC page
    stamps alongside real losses, which buries the finding. These are the same two
    predicates the rest of the pipeline already uses to tell apparatus from prose.
    """
    from sentence_reading.cite_refs import looks_like_prose_line

    if is_back_matter_sentence(fragment):
        return False
    if not looks_like_prose_line(fragment):
        return False
    return not is_front_or_reference_apparatus(fragment)


# design/350 — after design/349 removed the real losses, everything still listed was
# apparatus that is correctly dropped, and reporting it as lost prose buries the next
# real finding. Four shapes, each from the corpus:
#
#   author biography   `Her research is aimed at gaining fundamental insights in …`
#   author/affiliation `Allen,† Sungwoo Lee,† … ‡Department of Materials, Oxford, OX1 3PH`
#   reference entry    `367 of Astronomical Society of the Pacific Conference Series …`
#   figure axis labels `( FCH4in − FCH4out FCH4in ) H2 produced (µmol .min-1) CO produced …`
_AUTHOR_BIO = re.compile(
    r"\b(?:received (?:his|her|their) (?:PhD|Ph\.?D|M\.?Sc|B\.?Sc|bachelor|master|doctor)"
    r"|obtained (?:his|her|their) (?:PhD|Ph\.?D|degree|diploma)\b"
    r"|earned (?:his|her|their) (?:PhD|Ph\.?D|degree)\b"
    r"|(?:is|was|has been) (?:currently )?(?:a |an |the )?"
    r"(?:full |associate |assistant )?(?:professor|lecturer|researcher|research fellow"
    r"|PhD student|postdoc(?:toral)?\b)"
    r"|joined the [A-Z][^.]{0,60}(?:laboratory|group|department|institute)\b"
    r"|joined [A-Z][A-Za-z.\u2019' -]{2,40}(?:\u2019s|'s) (?:group|lab|laboratory)\b"
    r"|(?:his|her|their) research (?:interests?\b|focuses\b|is aimed at\b|centres? on\b))",
    re.I,
)
# Affiliation markers. Two or more footnote daggers, or a postal address tail after a
# department name, is an author block — never a results sentence.
_AFFIL_MARK = re.compile(r"[\u2020\u2021\u00a7\u00b6]")
_AFFIL_WORD = re.compile(
    r"\b(?:Department|Departamento|Institute|Instituto|Faculty|School|Laborator(?:y|ies)"
    r"|Universi(?:ty|dad|tat)|College|Academy of Sciences)\b"
)
# Figure and table axis labels: a unit in parentheses, more than once.
_UNIT_IN_PARENS = re.compile(
    r"\(\s*[\u00b5\u03bcmknMGT]?(?:mol|g|L|m|s|min|h|A|V|W|Pa|bar|K|eV|Hz)\b[^)]{0,14}\)"
)
# A supplementary file list: `Formation of the 855 line defect (AVI) Motion of kink …`.
# The format markers are what make it a list of downloads rather than a paragraph.
_SUPP_FILE_MARK = re.compile(r"\((?:AVI|MP4|MOV|WMV|PDF|DOCX?|XLSX?|ZIP|TIFF?|CIF)\)", re.I)
# A proceedings or series citation: `367 of Astronomical Society of the Pacific
# Conference Series (…, 2007), p.` — too few of `reference_signal_density`'s signals to
# reach its floor, because the authors are in the series name rather than an initials run.
_SERIES_CITE = re.compile(
    r"\b(?:Conference Series|Proceedings of|Proc\.|Ser\.|Lect(?:ure)?\.? Notes"
    r"|Symposium (?:Series|on))\b"
)
_YEAR = re.compile(r"\b(?:19|20)\d{2}\b")


def is_front_or_reference_apparatus(fragment: str) -> bool:
    """Journal front matter or a bibliography entry, not prose the reader lost."""
    from sentence_reading.cite_refs import reference_signal_density

    s = plain_text(fragment or "")
    if _AUTHOR_BIO.search(s):
        return True
    marks = len(_AFFIL_MARK.findall(s))
    # Two daggers plus a department name, or three on their own — an author block
    # carries one per author, and running prose carries none.
    if marks >= 3 or (marks >= 2 and _AFFIL_WORD.search(s)):
        return True
    if reference_signal_density(s) >= REF_SIGNAL_DENSITY_MAX:
        return True
    if _SERIES_CITE.search(s) and _YEAR.search(s):
        return True
    if len(_SUPP_FILE_MARK.findall(s)) >= 2:
        return True
    return len(_UNIT_IN_PARENS.findall(s)) >= 2




# design/345 — glyph corruption the extractor can introduce. One run of the Elsevier
# paper turned every `o` into a two-character sequence, 1,483 times, and those
# sentences went to the reader; the next run of the same PDF was clean. The PDF's own
# embedded text is deterministic and was correct both times, so it is the answer key.
_GREEK_IN_WORD = re.compile(r"[A-Za-z]{2,}[\u0370-\u03ff][A-Za-z]{2,}")
# `phen0men0n` — a digit standing where a letter belongs. Three letters before and two
# after keeps chemical tokens out: `co2`, `h2o`, `sp3d` and `mp3` all fail it.
_DIGIT_IN_WORD = re.compile(r"\b[a-z]{3,}[0-9][a-z]{2,}")
# A one-letter subscript with the word continuing after it. Real prose puts a space
# or punctuation after a subscript: `e<sub>g</sub> filling`, `t<sub>ion</sub>`. The
# Elsevier run produced `Pr?<sub>h</sub>t?<sub>h</sub>nic`, where the character before
# the subscript is not a letter either — so only the tail can be relied on.
_SUB_IN_WORD = re.compile(r"<sub>[a-z]</sub>(?=[A-Za-z])")
# Measured over twelve runs: a corrupted extraction scores 2.87 or 27.67 per 1000
# characters, a clean one 0.000 to 0.201. This is the geometric middle of that gap.
CORRUPTION_PER_1K_WARN = 0.75


def glyph_corruption_marks(text: str) -> int:
    """Signatures of a glyph that decoded to the wrong character.

    A Greek letter inside a Latin word, a digit inside a lowercase word, or a
    one-letter subscript wedged between letters are all impossible in real prose:
    `catalγst`, `phen0men0n`, `Pr?<sub>h</sub>t?<sub>h</sub>nic`.
    """
    s = text or ""
    return (
        len(_GREEK_IN_WORD.findall(s))
        + len(_DIGIT_IN_WORD.findall(s))
        + len(_SUB_IN_WORD.findall(s))
    )


def corruption_per_1k(text: str) -> float:
    s = text or ""
    if len(s) < 500:
        return 0.0
    return round(1000.0 * glyph_corruption_marks(s) / len(s), 3)


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


def _text_ruler(raw_text: str, sentences: list[Sentence]) -> dict[str, object]:
    """design/344 — never let the honest ruler break the ingest it is measuring."""
    try:
        ratio, missing = text_coverage(raw_text, sentences)
    except Exception:  # noqa: BLE001
        return {}
    return {"text_coverage": ratio, "text_missing_n": len(missing)}


def build_ingest_quality(
    *,
    raw_text: str,
    sentences: list[Sentence],
    chunk_stats: list[ChunkStat],
    ungrounded_ids: list[str],
    partial_debone_failed: list[int] | None = None,
    back_matter_dropped: int = 0,
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
        back_matter_dropped=int(back_matter_dropped),
        bib_chars_dropped=sum(s.bib_chars_dropped for s in chunk_stats),
        references_pin_rejected=[
            s.index
            for s in chunk_stats
            if s.references_pin_rejected and s.references_verdict != "kind"
        ],
        references_kind_rejected=[
            s.index
            for s in chunk_stats
            if s.references_pin_rejected and s.references_verdict == "kind"
        ],
        # design/330 — the bibliography is never practice text, so it must not
        # sit in the denominator and read as loss.
        coverage_ratio=coverage_excluding_references(raw_text, sentences),
        **_text_ruler(raw_text, sentences),
        glyph_corruption_per_1k=corruption_per_1k(
            " ".join(s.text or "" for s in sentences or [])
        ),
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
    from sentence_reading.cite_refs import reference_signal_density

    if chunk_kind(kept) != "substantive":
        return False
    whole = prose_chars(original)
    if whole <= 0:
        return False
    if (prose_chars(kept) / whole) < PIN_RESCUE_MIN_SHARE:
        return False
    # A split reference entry reads as prose line by line, so the region as a
    # whole has to be checked too.
    return reference_signal_density(kept) < REF_SIGNAL_DENSITY_MAX


def chunk_text_delivered(
    chunk_text: str, pairs: list[tuple[str, str]] | None
) -> tuple[float, list[str]]:
    """design/345 — what share of this chunk's prose came back, and which pieces did not.

    Reported, not gated. A gate needs a threshold, and the first attempt at one was
    derived by comparing stored sentences against a *fresh* extraction of the same
    PDF — which measures how much the extractor varies between calls, not how much
    the pipeline lost. Azure returned wildly different text for the same file on two
    runs, so that comparison could not support a decision.
    """
    sents = [Sentence(id=str(i), text=t, section=s) for i, (t, s) in enumerate(pairs or [])]
    return text_coverage(chunk_text, sents)


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
    for i in iq.references_kind_rejected:
        w.append(f"references_kind_rejected:{i}")
    # design/336 — `bib_chars_dropped` reached the cache and stopped there, so a
    # deletion of any size produced no warning string at all.
    if iq.bib_chars_dropped >= BIB_DROPPED_REPORT_CHARS:
        w.append(f"bib_chars_dropped:{iq.bib_chars_dropped}")
    if iq.back_matter_dropped:
        w.append(f"back_matter_dropped:{iq.back_matter_dropped}")
    # design/344 — a named count of prose that never reached the reader. The word-list
    # ratio read 0.85 to 0.97 on the same papers while every one of them was losing
    # real sentences.
    if iq.text_missing_n:
        w.append(f"text_missing:{iq.text_missing_n}")
    if iq.text_coverage < TEXT_COVERAGE_WARN:
        w.append(f"text_coverage_low:{iq.text_coverage:.2f}")
    # design/345 — the sentences the reader will say aloud contain characters the paper
    # did not print. One run turned every `o` into a two-character sequence, 1,483
    # times, and shipped; the next run of the same PDF was clean.
    if iq.glyph_corruption_per_1k >= CORRUPTION_PER_1K_WARN:
        w.append(f"glyph_corruption:{iq.glyph_corruption_per_1k:.2f}")
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
    """design/336 — kept as an alias; `practice_text_only` is the one definition.

    This function held the implausible-cut refusal while having no callers, so the
    guard never ran on the live denominator. Both names now resolve to the same
    code rather than drifting apart again.
    """
    return practice_text_only(raw)


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
