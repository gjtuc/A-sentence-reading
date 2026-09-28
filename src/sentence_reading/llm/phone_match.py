"""Compare two runs of pronunciation symbols.

design/368 — eSpeak used to produce the target symbols here. A dictionary
reading of the spelling is not the sound a voice makes, so the target now comes
from running the native audio through the same waveform model as the take, and
this module only cuts and compares. Nothing in here reads a dictionary.
"""

from __future__ import annotations

import re
import unicodedata

_STRESS = re.compile(r"[ˈˌ.ːˑ]")
# A tie joins two letters into one sound. A trailing mark colours the sound
# before it, so neither may open a new one.
_PHONE_TIE = "\u0361\u035c\u200d"
_PHONE_TRAIL = "ʰʲʷⁿˠˤ"
_THEIR_PHRASE = re.compile(r"\bthey(?:'re| are)\b", re.IGNORECASE)
_THEIR_WORD = {"their", "there", "they're"}
_OVERLAP_MIN = 0.72
_MIN_PHONES = 3


def canonicalize_sound_alikes(text: str) -> str:
    """Fold their / there / they're / they are, and number words, into one form."""
    folded = _THEIR_PHRASE.sub("their", text or "")
    parts = []
    for token in folded.split():
        key = token.strip(".,;:!?\"'").lower()
        if key in _THEIR_WORD:
            parts.append("their")
        elif key in NUMBER_WORD_DIGITS:
            parts.append(NUMBER_WORD_DIGITS[key])
        else:
            parts.append(token)
    return " ".join(parts)


# A printed `1` is read and heard as `one`, so both sides fold to the digit.
NUMBER_WORD_DIGITS = {
    "zero": "0", "one": "1", "two": "2", "three": "3", "four": "4",
    "five": "5", "six": "6", "seven": "7", "eight": "8", "nine": "9",
    "ten": "10", "eleven": "11", "twelve": "12", "thirteen": "13",
    "fourteen": "14", "fifteen": "15", "sixteen": "16", "seventeen": "17",
    "eighteen": "18", "nineteen": "19", "twenty": "20", "thirty": "30",
    "forty": "40", "fifty": "50", "sixty": "60", "seventy": "70",
    "eighty": "80", "ninety": "90",
}


def split_phone_units(ipa: str) -> list[str]:
    """One sound per item.

    A model may write a whole word as one run (`dɪspˈɜːʃən`) or one sound at a
    time. Comparing two runs needs both sides cut the same way, so a run is
    opened at every base letter and the marks that belong to it are carried
    along.
    """
    units: list[str] = []
    tied = False
    for ch in _STRESS.sub("", ipa or ""):
        if ch.isspace():
            tied = False
            continue
        if ch in _PHONE_TIE:
            if units:
                units[-1] += ch
                tied = True
            continue
        if unicodedata.combining(ch) or ch in _PHONE_TRAIL:
            if units:
                units[-1] += ch
            continue
        if tied and units:
            units[-1] += ch
            tied = False
            continue
        units.append(ch)
    return units


def normalize_phones(ipa: str) -> list[str]:
    return split_phone_units(ipa)


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


def best_window_overlap(left: list[str], flat: list[str]) -> float:
    """Best overlap of `left` against any stretch of `flat`.

    The stretch is tried one sound short through two sounds long: the model drops
    a sound less often than it splits one in two.
    """
    span = len(left)
    if not left or not flat:
        return 0.0
    best = 0.0
    starts = max(1, len(flat) - span + 1)
    for start in range(starts):
        for width in range(max(1, span - 1), span + 3):
            right = flat[start : start + width]
            if not right:
                continue
            got = overlap_ratio(left, right)
            if got > best:
                best = got
    return best


def phones_close(target: str, heard: str) -> bool:
    """True when `target` is heard anywhere in `heard`.

    design/366 — the waveform model returns one run of sounds for the whole take,
    so a word has to be looked for inside that run. Comparing the run end to end
    only worked when the take held one word.
    """
    left = normalize_phones(target)
    right = normalize_phones(heard)
    if len(left) < _MIN_PHONES:
        return False
    return best_window_overlap(left, right) >= _OVERLAP_MIN
