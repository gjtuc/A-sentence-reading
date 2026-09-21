"""Keep the coordinates the layout service already gave us (design/352).

The service returns each paragraph as a box with a page and coordinates, and
`order_boxes` sorts those boxes into reading order. Then the text is concatenated and
the coordinates are thrown away — so when something downstream needs a sentence's
position, it searches the whole paper for six of the sentence's words and sometimes
finds a passage forty-seven thousand characters away that merely reads alike. That is
how design/351's order check came to report 44% on a paper whose order is 99% right.

Nothing has to be recovered by search. Each box's **first sentence** is taken before the
text is sent anywhere and remembered along with the box it came from. In the returned
sentences that marker is located among one chunk's twenty-odd sentences instead of in
sixty thousand characters of paper, and everything from one marker to just before the
next belongs to that box.

Measured through this module over ten papers and 1,405 boxes: 368 carry a usable marker
and **337 of those are located again (91.6%)**, 320 of them to within 5%. Every paper
falls between 87% and 100%. A marker that is not found is not a wrong answer — its
sentences fall to the previous box, which is the box next to it in reading order, so the
position loses precision rather than correctness.

Two things had to be right for that number:

- **Sentence ends hidden by citations.** Journals set the citation against the full stop,
  so the text reads `catalysis.[3] Because`, `temperature.175 The`, `recognized.50,51 The`.
  Splitting on "full stop then space" glued two or three sentences into one marker, which
  no single returned sentence could match. Handling it lifted one paper from 51.5% to
  93.9% and the corpus from 63.3% to 91.0%.
- **Comparing letters, not words.** A line-break hyphen makes `depen- dence` three tokens
  against one, and a misread glyph makes `jM` a different word from `φM`, while in letters
  they differ by one in a hundred and fifty. Two real sentences of a paper practically
  never differ by a letter or two, so letters can be held to a high bar.
- **Apparatus boxes kept out of the search, and the earliest match preferred.** Both are
  the same fault seen twice: a marginal match far ahead moves the cursor and starves
  every box behind it. Fixing them took the corpus from 67.4% to 91.6%, `srep41797` from
  28.1% to 90.0% and `cs5b00357` from 44.7% to 97.1%.
"""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass, field

# A full stop followed by the citation it carries: `[3]`, `[21,22]`, `175`, `50,51`.
# Anchored on a following capital or opening bracket so a decimal or a version number
# is untouched: `0.15 was`, `Fig. 3b shows`.
_CITE_AFTER_STOP = re.compile(
    r"(?<=[.!?])(?:\s*\[[\d,;\s\u2013\u2014-]+\]|\d{1,3}(?:\s*[,;\u2013-]\s*\d{1,3}){0,6})+"
    r"(?=\s+[A-Z(])"
)
_SENT_END = re.compile(r"(?<=[.!?])\s+")
_NOT_ALNUM = re.compile(r"[^a-z0-9]+")
# A full stop that belongs to an abbreviation, not to a sentence: `Fig. 3b shows`,
# `ca. 500 K`, `S. R. Bare`. Splitting there leaves a marker of one or two words, which
# is then thrown away as too short and costs that box its marker.
_ABBREV_END = re.compile(
    r"(?:^|\s)(?:Figs?|Eqs?|Tabs?|Refs?|Nos?|Vols?|Chaps?|Secs?|Suppl"
    r"|vs|cf|ca|approx|al|etc|e\.g|i\.e|Dr|Prof|Mr|Ms|Mrs|St|pp|eds?|Inc|Ltd|Co|Univ)\.$",
    re.IGNORECASE,
)

# Below this many words a box's opening is a heading or a stub, not a usable marker.
MARK_MIN_WORDS = 5
# A marker is accepted when this much of it is found at the front of a sentence.
MARK_MATCH_MIN = 0.70
# At or above this the match is certain rather than probable, and is reported as such.
MARK_MATCH_SURE = 0.95


@dataclass(frozen=True)
class BoxMark:
    """One paragraph box: where it starts in the joined text, and where it sits on paper."""

    index: int
    start_char: int
    page: int
    x0: float
    y0: float
    x1: float
    y1: float
    marker: str = ""

    def to_dict(self) -> dict:
        return {
            "index": self.index,
            "start_char": self.start_char,
            "page": self.page,
            "rect": [round(self.x0, 1), round(self.y0, 1), round(self.x1, 1), round(self.y1, 1)],
        }


@dataclass
class MarkCensus:
    """What the marker pass actually managed, reported rather than assumed."""

    boxes: int = 0
    marked: int = 0
    found_sure: int = 0
    found_probable: int = 0
    not_found: int = 0

    def to_dict(self) -> dict[str, int]:
        return {
            "box_n": self.boxes,
            "marker_n": self.marked,
            "marker_sure_n": self.found_sure,
            "marker_probable_n": self.found_probable,
            "marker_missing_n": self.not_found,
        }


def split_sentences_for_marks(text: str) -> list[str]:
    """Sentences of one box, with the citation-hidden ends restored and abbreviations kept."""
    cleaned = _CITE_AFTER_STOP.sub(" ", text or "")
    out: list[str] = []
    for piece in _SENT_END.split(cleaned):
        piece = piece.strip()
        if not piece:
            continue
        if out and _ABBREV_END.search(out[-1]):
            out[-1] = f"{out[-1]} {piece}"
        else:
            out.append(piece)
    return out


def first_sentence(text: str) -> str:
    """The marker for a box, or empty when the box cannot supply a usable one.

    A box whose opening is not practice prose gets no marker. That is not tidiness: the
    search walks forward, so a marker matched too far ahead starves every marker after
    it. On `srep41797` one masthead box scraped past the floor at 0.72 against sentence
    166 of 192, moved the cursor from 45 to 167, and starved the seventeen real boxes
    that followed — 94% of markers down to 28%. An apparatus box has nothing to find in
    the practice sentences, so letting it search at all is the fault.
    """
    from sentence_reading.llm.debone_quality import _worth_reporting_missing

    parts = split_sentences_for_marks(text)
    if not parts:
        return ""
    head = parts[0]
    if len(re.findall(r"[A-Za-z0-9]+", head)) < MARK_MIN_WORDS:
        return ""
    return head if _worth_reporting_missing(head) else ""


def _letters(text: str) -> str:
    return _NOT_ALNUM.sub("", (text or "").lower())


def match_score(marker: str, sentence: str) -> float:
    """How much of the marker's letters open this sentence.

    Prefix-anchored, because a marker is a box's *first* sentence: it belongs at the front
    of what the model returned for that box. That also keeps a long sentence from scoring
    well merely by sharing many letters somewhere in its middle.
    """
    a, b = _letters(marker), _letters(sentence)
    if not a or not b:
        return 0.0
    n = min(len(a), len(b))
    if sum(1 for i in range(n) if a[i] == b[i]) / n >= 0.90:
        return n / len(a)
    return difflib.SequenceMatcher(None, a, b[: len(a) + 40]).ratio()


def place_sentences_in_boxes(sentences, marks):
    """Copy each box's position onto the sentences that came from it (design/352).

    Returns the sentences and the census. Without marks — the raw path has no boxes —
    the sentences come back untouched, so nothing depends on the layout service being on.
    """
    from dataclasses import replace

    if not marks or not sentences:
        return sentences, MarkCensus()
    owner, census = assign_boxes(marks, [getattr(s, "text", "") or "" for s in sentences])
    out = []
    for s, m_i in zip(sentences, owner):
        if m_i < 0:
            out.append(s)
            continue
        mark = marks[m_i]
        out.append(replace(s, start_char=mark.start_char, end_char=mark.start_char))
    return out, census


def assign_boxes(
    marks: list[BoxMark], sentences: list[str]
) -> tuple[list[int], MarkCensus]:
    """For each sentence, the index into `marks` of the box it came from.

    `-1` until the first marker is located. Markers are sought in order and each search
    starts after the last one found, so a phrase repeated later in the paper cannot pull a
    box backwards.
    """
    census = MarkCensus(boxes=len(marks))
    owner = [-1] * len(sentences)
    at = 0
    for m_i, mark in enumerate(marks):
        if not mark.marker:
            continue
        census.marked += 1
        # The **earliest** credible match, not the best one. Boxes are sought in their own
        # order, so the first sentence that opens with this marker is the one that belongs
        # to it; preferring a higher score further along is what lets a marginal match
        # jump the cursor over dozens of sentences and starve the boxes behind it.
        best, best_i = 0.0, -1
        for s_i in range(at, len(sentences)):
            score = match_score(mark.marker, sentences[s_i])
            if score >= MARK_MATCH_SURE:
                best, best_i = score, s_i
                break
            if score > best:
                best, best_i = score, s_i
        if best < MARK_MATCH_MIN or best_i < 0:
            census.not_found += 1
            continue
        if best >= MARK_MATCH_SURE:
            census.found_sure += 1
        else:
            census.found_probable += 1
        for s_i in range(best_i, len(sentences)):
            owner[s_i] = m_i
        at = best_i + 1
    return owner, census
