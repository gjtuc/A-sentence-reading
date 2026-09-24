"""Pronunciation symbols for the spoken line, and a sound-overlap score.

The symbols come from eSpeak on the whole spoken sentence. They are the
dictionary reading of the recognized text, not a waveform model.
"""

from __future__ import annotations

import re
import shutil
import subprocess

_STRESS = re.compile(r"[ˈˌ.ːˑ]")
_THEIR_PHRASE = re.compile(r"\bthey(?:'re| are)\b", re.IGNORECASE)
_THEIR_WORD = {"their", "there", "they're"}
_WORD = re.compile(r"[A-Za-z0-9]+(?:'[A-Za-z]+)?")
_OVERLAP_MIN = 0.72
_MIN_PHONES = 3


def canonicalize_sound_alikes(text: str) -> str:
    """Fold their / there / they're / they are into one written form."""
    folded = _THEIR_PHRASE.sub("their", text or "")
    parts = []
    for token in folded.split():
        key = token.strip(".,;:!?\"'").lower()
        if key in _THEIR_WORD:
            parts.append("their")
        else:
            parts.append(token)
    return " ".join(parts)


def normalize_phones(ipa: str) -> list[str]:
    raw = _STRESS.sub("", ipa or "")
    return [piece for piece in raw.split() if piece]


def overlap_ratio(left: list[str], right: list[str]) -> float:
    if not left or not right:
        return 0.0
    rows = len(left) + 1
    cols = len(right) + 1
    dist = [[0] * cols for _ in range(rows)]
    for i in range(rows):
        dist[i][0] = i
    for j in range(cols):
        dist[0][j] = j
    for i in range(1, rows):
        for j in range(1, cols):
            cost = 0 if left[i - 1] == right[j - 1] else 1
            dist[i][j] = min(
                dist[i - 1][j] + 1,
                dist[i][j - 1] + 1,
                dist[i - 1][j - 1] + cost,
            )
    longest = max(len(left), len(right))
    return 1.0 - (dist[-1][-1] / float(longest))


def phones_close(target: str, heard: str) -> bool:
    """True when two symbol strings are the same sound and long enough."""
    left = normalize_phones(target)
    right = normalize_phones(heard)
    if len(left) < _MIN_PHONES:
        return False
    return overlap_ratio(left, right) >= _OVERLAP_MIN


def espeak_ipa_words(sentence: str) -> list[str]:
    """One IPA string per word, from one eSpeak call on the whole sentence."""
    exe = shutil.which("espeak-ng") or shutil.which("espeak")
    text = (sentence or "").strip()
    if not exe or not text:
        return []
    try:
        done = subprocess.run(
            [exe, "-v", "en-us", "-q", "--ipa=3", text],
            capture_output=True,
            text=True,
            timeout=8,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return []
    raw = (done.stdout or "").replace("\n", " ").strip()
    if not raw:
        return []
    words: list[str] = []
    for part in raw.split():
        phones = part.replace("_", " ").strip()
        if phones:
            words.append(phones)
    return words


def assign_span_phones(spoken: str, weights: list[int]) -> list[str]:
    phones, _report = phone_assign(spoken, weights)
    return phones


def phone_assign(spoken: str, weights: list[int]) -> tuple[list[str], dict[str, object]]:
    """Phones per slot, plus why the line was kept or blanked."""
    exe = shutil.which("espeak-ng") or shutil.which("espeak")
    ipa_words = espeak_ipa_words(spoken) if exe else []
    words = list(_WORD.finditer(spoken or ""))
    report: dict[str, object] = {
        "phone_code": "ok",
        "phone_word_n": len(words),
        "phone_ipa_n": len(ipa_words),
        "phone_weight_n": len(weights),
        "phone_filled_n": 0,
        "phone_espeak": 1 if exe else 0,
    }
    if not exe:
        report["phone_code"] = "espeak_missing"
        return [""] * len(weights), report
    if not ipa_words:
        report["phone_code"] = "espeak_empty"
        return [""] * len(weights), report
    if len(ipa_words) != len(words):
        report["phone_code"] = "count_mismatch"
        return [""] * len(weights), report
    cursor = 0
    word_i = 0
    out: list[str] = []
    for weight in weights:
        cursor = _skip_gap(spoken, cursor)
        end = min(len(spoken), cursor + max(weight, 0))
        pieces: list[str] = []
        while word_i < len(words) and words[word_i].end() <= end and words[word_i].start() >= cursor:
            pieces.append(ipa_words[word_i])
            word_i += 1
        out.append(" ".join(pieces))
        cursor = end
    report["phone_filled_n"] = sum(1 for item in out if item)
    return out, report


def _skip_gap(spoken: str, cursor: int) -> int:
    n = len(spoken)
    while cursor < n and spoken[cursor] in " \n\t\r":
        cursor += 1
    while cursor < n and not (spoken[cursor].isalnum() or spoken[cursor] == "'"):
        cursor += 1
        while cursor < n and spoken[cursor] in " \n\t\r":
            cursor += 1
    return cursor
