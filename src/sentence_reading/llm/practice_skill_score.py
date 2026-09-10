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
