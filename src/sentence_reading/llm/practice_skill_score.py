"""design/212 — content-word multiset coverage (pure; shared test vectors)."""

from __future__ import annotations

import re
from collections import Counter

_TAG_RE = re.compile(r"<[^>]+>")
_PUNCT_RE = re.compile(r"[^\w\s']+", re.UNICODE)
_SPACE_RE = re.compile(r"\s+")

# Minimal English function-word set (versioned with CONTENT_WORD_LIST_V).
CONTENT_WORD_LIST_V = 1
_FUNCTION_WORDS = frozenset(
    {
        "a",
        "an",
        "the",
        "and",
        "or",
        "but",
        "if",
        "in",
        "on",
        "at",
        "to",
        "for",
        "of",
        "as",
        "by",
        "with",
        "from",
        "into",
        "onto",
        "over",
        "under",
        "is",
        "are",
        "was",
        "were",
        "be",
        "been",
        "being",
        "am",
        "do",
        "does",
        "did",
        "have",
        "has",
        "had",
        "will",
        "would",
        "shall",
        "should",
        "can",
        "could",
        "may",
        "might",
        "must",
        "that",
        "this",
        "these",
        "those",
        "it",
        "its",
        "they",
        "them",
        "their",
        "we",
        "our",
        "you",
        "your",
        "he",
        "she",
        "his",
        "her",
        "i",
        "me",
        "my",
        "not",
        "no",
        "nor",
        "so",
        "than",
        "then",
        "there",
        "here",
        "when",
        "where",
        "which",
        "who",
        "whom",
        "what",
        "how",
        "also",
        "just",
        "only",
        "very",
        "too",
        "up",
        "out",
        "about",
        "into",
        "such",
        "per",
    }
)


def normalize_skill_text(text: str | None) -> str:
    if text is None:
        return ""
    if not isinstance(text, str):
        text = str(text)
    t = _TAG_RE.sub(" ", text)
    t = t.lower().replace("\u2019", "'").replace("\u2018", "'")
    t = _PUNCT_RE.sub(" ", t)
    t = _SPACE_RE.sub(" ", t).strip()
    return t


def tokenize_skill(text: str | None) -> list[str]:
    n = normalize_skill_text(text)
    if not n:
        return []
    return n.split(" ")


def content_words(text: str | None) -> list[str]:
    return [w for w in tokenize_skill(text) if w and w not in _FUNCTION_WORDS]


def content_word_coverage(expected_spoken: str | None, heard: str | None) -> dict:
    """Order-insensitive multiset coverage of content words.

    accuracy = covered / |ref|. Insertions in heard do not reduce score.
    """
    ref = content_words(expected_spoken)
    hyp = content_words(heard)
    if not ref:
        return {
            "ok": False,
            "error": "empty_content_ref",
            "accuracy": None,
            "ref_n": 0,
            "hit_n": 0,
            "list_v": CONTENT_WORD_LIST_V,
        }
    need = Counter(ref)
    have = Counter(hyp)
    hit = 0
    for w, n in need.items():
        hit += min(n, have.get(w, 0))
    acc = hit / float(len(ref))
    return {
        "ok": True,
        "accuracy": round(acc, 4),
        "ref_n": len(ref),
        "hit_n": hit,
        "list_v": CONTENT_WORD_LIST_V,
    }


def spoken_slot_coverage(
    display: str | None,
    spoken: str | None,
    spans: list[dict],
    heard: str | None,
) -> dict:
    """One printed token is one slot. Every spoken piece of that token must be heard."""
    slots = _spoken_slots(display or "", spoken or "", spans)
    if not slots:
        return {
            "ok": False,
            "error": "empty_slot_ref",
            "accuracy": None,
            "ref_n": 0,
            "hit_n": 0,
            "list_v": 2,
            "missed": [],
        }
    have = Counter(tokenize_skill(heard))
    hit = 0
    missed: list[dict[str, int]] = []
    for start, end, tokens in slots:
        if _take_spoken_slot(tokens, have):
            hit += 1
        else:
            missed.append({"start": start, "end": end})
    acc = hit / float(len(slots))
    return {
        "ok": True,
        "accuracy": round(acc, 4),
        "ref_n": len(slots),
        "hit_n": hit,
        "list_v": 2,
        "missed": missed,
    }


def _spoken_slots(
    display: str, spoken: str, spans: list[dict]
) -> list[tuple[int, int, list[str]]]:
    if not display or not spoken:
        return []
    scored = []
    for span in spans:
        weight = int(span.get("weight") or 0)
        start = int(span.get("start") or 0)
        end = int(span.get("end") or 0)
        if weight > 0 and 0 <= start < end <= len(display):
            scored.append((start, end, weight))
    if not scored:
        return []
    cursor = 0
    out: list[tuple[int, int, list[str]]] = []
    for start, end, weight in scored:
        while cursor < len(spoken) and spoken[cursor] in " \n\t\r":
            cursor += 1
        piece_end = cursor + weight
        if piece_end > len(spoken):
            return []
        tokens = tokenize_skill(spoken[cursor:piece_end])
        cursor = piece_end
        if not tokens:
            return []
        out.append((start, end, tokens))
    return out


def _take_spoken_slot(tokens: list[str], have: Counter) -> bool:
    ok = True
    for token in tokens:
        left = have.get(token, 0)
        if left <= 0:
            ok = False
            continue
        if left == 1:
            del have[token]
        else:
            have[token] = left - 1
    return ok
