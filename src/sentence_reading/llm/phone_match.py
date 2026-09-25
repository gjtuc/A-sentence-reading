"""Pronunciation symbols for the spoken line, and a sound-overlap score.

The symbols come from eSpeak on the whole spoken sentence. They are the
dictionary reading of the recognized text, not a waveform model.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import unicodedata

_STRESS = re.compile(r"[ˈˌ.ːˑ]")
# A tie joins two letters into one sound. A trailing mark colours the sound
# before it, so neither may open a new one.
_PHONE_TIE = "\u0361\u035c\u200d"
_PHONE_TRAIL = "ʰʲʷⁿˠˤ"
_THEIR_PHRASE = re.compile(r"\bthey(?:'re| are)\b", re.IGNORECASE)
_THEIR_WORD = {"their", "there", "they're"}
_WORD = re.compile(r"[A-Za-z0-9]+(?:'[A-Za-z]+)?")
_OVERLAP_MIN = 0.72
_MIN_PHONES = 3
_WORD_IPA: dict[str, str] = {}
_WORD_IPA_MAX = 20000


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

    eSpeak writes a whole word as one run (`dɪspˈɜːʃən`) while the waveform
    model writes one sound at a time. Comparing the two needs both sides cut
    the same way, so a run is opened at every base letter and the marks that
    belong to it are carried along.
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


def phones_close(target: str, heard: str) -> bool:
    """True when two symbol strings are the same sound and long enough."""
    left = normalize_phones(target)
    right = normalize_phones(heard)
    if len(left) < _MIN_PHONES:
        return False
    return overlap_ratio(left, right) >= _OVERLAP_MIN


def _espeak_ipa(exe: str, text: str) -> list[str]:
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
    out: list[str] = []
    for part in raw.split():
        phones = part.replace("_", " ").strip()
        if phones:
            out.append(phones)
    return out


def espeak_ipa_words(sentence: str) -> list[str]:
    """One IPA string per word, from one eSpeak call on the whole sentence."""
    exe = shutil.which("espeak-ng") or shutil.which("espeak")
    text = (sentence or "").strip()
    if not exe or not text:
        return []
    return _espeak_ipa(exe, text)


def espeak_ipa_per_word(exe: str, words: list[str]) -> list[str]:
    """IPA for each word on its own, so a merged pair cannot shift the line.

    eSpeak runs a whole clause through its phrase rules, and it joins
    unstressed helpers (`have been` -> one token). One word per call keeps the
    count equal to the printed words. Repeat words come from the cache, so a
    paper pays for its vocabulary once.
    """
    out: list[str] = []
    for word in words:
        key = word.casefold()
        hit = _WORD_IPA.get(key)
        if hit is None:
            pieces = _espeak_ipa(exe, word)
            hit = " ".join(pieces).strip()
            if len(_WORD_IPA) < _WORD_IPA_MAX:
                _WORD_IPA[key] = hit
        out.append(hit)
    return out


def assign_span_phones(spoken: str, weights: list[int]) -> list[str]:
    phones, _report = phone_assign(spoken, weights)
    return phones


def phone_assign(spoken: str, weights: list[int]) -> tuple[list[str], dict[str, object]]:
    """Phones per slot, plus why the line was kept or blanked."""
    exe = shutil.which("espeak-ng") or shutil.which("espeak")
    ipa_words = espeak_ipa_words(spoken) if exe else []
    words = list(_WORD.finditer(spoken or ""))
    code = "ok"
    repair_n = 0
    if exe and len(ipa_words) != len(words) and words:
        # A merged pair shifted every later word. Ask per word instead of
        # dropping the whole line's symbols.
        ipa_words = espeak_ipa_per_word(exe, [w.group(0) for w in words])
        repair_n = len(words)
        code = "repaired"
    report: dict[str, object] = {
        "phone_code": code,
        "phone_word_n": len(words),
        "phone_ipa_n": len(ipa_words),
        "phone_weight_n": len(weights),
        "phone_filled_n": 0,
        "phone_repair_n": repair_n,
        "phone_blank_word_n": sum(1 for item in ipa_words if not item),
        "phone_espeak": 1 if exe else 0,
        # word=phones pairs, so a merged pair like `have been` is visible in the
        # log instead of just a count.
        "phone_pairs": _pair_words(words, ipa_words),
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


def _pair_words(words: list, ipa_words: list[str]) -> str:
    """`word=phones` for each printed word, with a blank when eSpeak ran short."""
    out: list[str] = []
    for i, word in enumerate(words):
        text = word.group(0) if hasattr(word, "group") else str(word)
        phones = ipa_words[i] if i < len(ipa_words) else ""
        out.append(f"{text}={phones}")
    extra = ipa_words[len(words):]
    for phones in extra:
        out.append(f"?={phones}")
    return " | ".join(out)


def _skip_gap(spoken: str, cursor: int) -> int:
    n = len(spoken)
    while cursor < n and spoken[cursor] in " \n\t\r":
        cursor += 1
    while cursor < n and not (spoken[cursor].isalnum() or spoken[cursor] == "'"):
        cursor += 1
        while cursor < n and spoken[cursor] in " \n\t\r":
            cursor += 1
    return cursor
