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


#: design/365 — one pronunciation written two ways. The transcript comes back in
#: whatever orthography the recognizer prefers, so a correctly read `vapour`
#: returns as `vapor` and the slot scores zero. Mirrors `kSpellingPairs`.
SPELLING_PAIRS: tuple[tuple[str, str], ...] = (
    ("vapour", "vapor"),
    ("vapours", "vapors"),
    ("sulphur", "sulfur"),
    ("sulphate", "sulfate"),
    ("sulphide", "sulfide"),
    ("aluminium", "aluminum"),
    ("caesium", "cesium"),
    ("colour", "color"),
    ("behaviour", "behavior"),
    ("favour", "favor"),
    ("neighbour", "neighbor"),
    ("fibre", "fiber"),
    ("fibres", "fibers"),
    ("centre", "center"),
    ("centred", "centered"),
    ("metre", "meter"),
    ("metres", "meters"),
    ("nanometre", "nanometer"),
    ("nanometres", "nanometers"),
    ("micrometre", "micrometer"),
    ("millimetre", "millimeter"),
    ("centimetre", "centimeter"),
    ("kilometre", "kilometer"),
    ("litre", "liter"),
    ("litres", "liters"),
    ("millilitre", "milliliter"),
    ("millilitres", "milliliters"),
    ("analyse", "analyze"),
    ("analysed", "analyzed"),
    ("analysing", "analyzing"),
    ("catalyse", "catalyze"),
    ("catalysed", "catalyzed"),
    ("ionisation", "ionization"),
    ("oxidising", "oxidizing"),
    ("oxidised", "oxidized"),
    ("carbonisation", "carbonization"),
    ("polarisation", "polarization"),
    ("isomerisation", "isomerization"),
    ("characterisation", "characterization"),
    ("utilise", "utilize"),
    ("labelling", "labeling"),
    ("modelling", "modeling"),
    ("programme", "program"),
    ("ageing", "aging"),
    ("grey", "gray"),
    ("practise", "practice"),
    ("licence", "license"),
    ("defence", "defense"),
)

_SPELLING_PARTNER: dict[str, str] = {}
for _a, _b in SPELLING_PAIRS:
    _SPELLING_PARTNER[_a] = _b
    _SPELLING_PARTNER[_b] = _a

#: design/365 — an element symbol the voice reads as the element name. The
#: spoken text keeps `Ni` while the voice says "nickel". One-directional, or a
#: two-letter match would let short words through. Mirrors
#: `kElementSymbolNames`.
ELEMENT_SYMBOL_NAMES: dict[str, str] = {
    "ni": "nickel",
    "pt": "platinum",
    "fe": "iron",
    "co": "cobalt",
    "cu": "copper",
    "al": "aluminium",
    "ba": "barium",
    "ce": "cerium",
    "zn": "zinc",
    "mg": "magnesium",
    "mn": "manganese",
    "ti": "titanium",
    "zr": "zirconium",
    "ru": "ruthenium",
    "rh": "rhodium",
    "pd": "palladium",
    "ag": "silver",
    "au": "gold",
    "si": "silicon",
}

_DIGIT_LETTER_RUN = re.compile(r"^(\d+)([a-z]+)$")
_LETTER_DIGIT_RUN = re.compile(r"^([a-z]+)(\d+)$")
_SLOT_HAS_SOUND = re.compile(r"[^\W_]", re.UNICODE)


def split_digit_letter_run(token: str) -> list[str]:
    """design/365 — `2p` -> `2`, `p`; `co2` -> `co`, `2`. Empty otherwise."""
    m = _DIGIT_LETTER_RUN.match(token) or _LETTER_DIGIT_RUN.match(token)
    return [m.group(1), m.group(2)] if m else []


def strip_apostrophes(token: str) -> str:
    """design/365 — a possessive mark is not a sound. `catalysts'` -> `catalysts`."""
    return token.replace("'", "")


def slot_tokens_scorable(tokens: list[str]) -> bool:
    """A slot with no letter and no digit cannot be heard.

    `catalysts'` left the apostrophe as its own slot, so that line could never
    score above two thirds no matter how it was read.
    """
    return any(_SLOT_HAS_SOUND.search(token) for token in tokens)


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
    from sentence_reading.llm.phone_match import canonicalize_sound_alikes

    have = Counter(tokenize_skill(canonicalize_sound_alikes(heard or "")))
    # design/365 — `Ni 2p` is read "nickel two pee" and comes back as one token
    # `2p`, while the aligner made `2` and `p` two slots. Both pieces really were
    # spoken, so both may be claimed from the joined token.
    for token in list(have):
        for piece in split_digit_letter_run(token):
            have[piece] += have[token]
        bare = strip_apostrophes(token)
        if bare and bare != token:
            have[bare] += have[token]
    hit = 0
    missed: list[dict[str, int]] = []
    for start, end, _tokens, match in slots:
        if _take_spoken_slot(match, have):
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
) -> list[tuple[int, int, list[str], list[str]]]:
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
    out: list[tuple[int, int, list[str], list[str]]] = []
    for start, end, weight in scored:
        cursor = _skip_spoken_gap(spoken, cursor)
        piece_end = cursor + weight
        if piece_end > len(spoken):
            return []
        from sentence_reading.llm.phone_match import canonicalize_sound_alikes

        piece = spoken[cursor:piece_end]
        tokens = tokenize_skill(piece)
        # design/365 — fold the slot side the same way as the heard side for the
        # compare only, or a spoken `two` can only be claimed by a transcript
        # that wrote the digit. The review still asks for the spoken word.
        match = tokenize_skill(canonicalize_sound_alikes(piece))
        cursor = piece_end
        if tokens and not slot_tokens_scorable(tokens):
            # Punctuation only: consume the piece, do not open a slot for it.
            continue
        if not tokens:
            return []
        out.append((start, end, tokens, match or tokens))
    return out


def _skip_spoken_gap(spoken: str, cursor: int) -> int:
    """Skip the same marks the aligner skipped before measuring the next word."""
    n = len(spoken)
    while cursor < n and spoken[cursor] in " \n\t\r":
        cursor += 1
    while cursor < n and not (spoken[cursor].isalnum() or spoken[cursor] == "'"):
        cursor += 1
        while cursor < n and spoken[cursor] in " \n\t\r":
            cursor += 1
    return cursor


def _take_spoken_slot(tokens: list[str], have: Counter) -> bool:
    if (
        len(tokens) >= 2
        and all(len(token) == 1 and token.isalpha() for token in tokens)
    ):
        joined = "".join(tokens)
        left = have.get(joined, 0)
        if left > 0:
            if left == 1:
                del have[joined]
            else:
                have[joined] = left - 1
            return True
    ok = True
    for token in tokens:
        if not take_skill_token(token, have):
            ok = False
    return ok


def _token_forms(token: str) -> list[str]:
    """The same word with or without a trailing `s`, plus design/365 variants.

    `1 nm` is read as `nanometers` while a speaker says `nanometer`, and neither
    is a mistake. Nor is `vapor` for a correctly read `vapour`, or `nickel` for
    the printed `Ni` the voice reads out as the element name. A possessive
    apostrophe is not a sound at all, so `catalysts'` and `catalysts` are one
    word.
    """
    out = [token]

    def add(form: str | None) -> None:
        if form and form not in out:
            out.append(form)

    bare = strip_apostrophes(token)
    add(bare)
    element = ELEMENT_SYMBOL_NAMES.get(bare)
    add(element)
    partner = _SPELLING_PARTNER.get(bare)
    add(partner)
    for base in (bare, element, partner):
        if not base or len(base) < 3:
            continue
        add(base[:-1] if base.endswith("s") else base + "s")
    return out


def take_skill_token(token: str, have: Counter) -> bool:
    for form in _token_forms(token):
        left = have.get(form, 0)
        if left <= 0:
            continue
        if left == 1:
            del have[form]
        else:
            have[form] = left - 1
        return True
    return False
