"""The paper's own letters, placed by the layout service's boxes (design/346).

design/345 found that the layout service's *reading* of a page varies between calls:
one run of an Elsevier paper turned every `o` into a two-character sequence 1,483
times, and the next run of the same file was clean. The PDF's embedded text does not
vary and was correct every time.

The two strengths are separable. The service is good at saying *where* a paragraph is
and *in what order* the paragraphs run — a job the embedded text cannot do, since it
carries no column or role structure. So keep the boxes and take the letters from the
PDF.

No similarity matching is needed: the boxes carry page coordinates in PDF points, so
the words inside one can be asked for directly.

Measured over four papers, 700 paragraphs of 80 characters or more:

    the service's words present in the clip   median 1.0000
    the clip's words present in the service   median 1.0000
    word *order* similarity                   median 1.0000, none broken
    paragraphs below 0.80 agreement           5

and every one of those five is identified below.
"""

from __future__ import annotations

import re
from collections import Counter

# Words whose centre falls inside the box. `get_text(clip=...)` keeps any line that
# *touches* the rect and keeps it whole, so a neighbouring line two points away
# arrives in full: on Scientific Reports that pulled in roughly as many foreign words
# as the paragraph had (agreement 0.549 over 91 paragraphs, 64 of them contaminated).
# Centre containment brought that to 0 of 91.
BOX_PAD_PT = 2.0

# Below this many characters the service's text is kept. Short boxes are headings and
# figure-internal labels: the PDF renders `ABSTRACT` letter-spaced as `A B S T R A C T`,
# which would break heading recognition, and axis ticks like `0.0 0.1 0.2` are drawn
# inside the figure image where the PDF has no text at all.
MIN_CHARS_TO_REPLACE = 80

# Below this agreement the clip is refused *as long as the service's reading looks
# sound*. The condition matters: when corruption is severe the two readings disagree
# everywhere, so agreement alone would refuse the repair exactly where it is needed.
# The lowest legitimate paragraph of the 700 scores 0.783.
MIN_AGREEMENT = 0.70

# A word this long that the service did not also read is a font without space glyphs.
# One RSC paragraph reads `transferredchargeishalfoftheamountofthedonorconcentration`
# as a single token; substituting it would be worse than the corruption this repair
# exists to fix. Across 697 clips the longest word is 24 letters — that paragraph —
# and the longest legitimate one is 19 (`hydrodechlorination`).
MAX_WORD_LETTERS = 20

_WORD = re.compile(r"[A-Za-z0-9]+")


def _words(text: str) -> list[str]:
    return _WORD.findall((text or "").lower())


def agreement(azure_text: str, pdf_text: str) -> float:
    """Share of the service's words that the PDF clip also carries."""
    want = _words(azure_text)
    if not want:
        return 1.0
    have = Counter(_words(pdf_text))
    hit = sum(min(n, have.get(w, 0)) for w, n in Counter(want).items())
    return hit / len(want)


def page_words(page) -> list[tuple[float, float, float, float, str]]:
    """Every word on the page with its rectangle, in the page's own reading order."""
    out = []
    for w in page.get_text("words") or []:
        out.append((float(w[0]), float(w[1]), float(w[2]), float(w[3]), str(w[4])))
    return out


def text_in_box(
    words: list[tuple[float, float, float, float, str]],
    x0: float,
    y0: float,
    x1: float,
    y1: float,
    *,
    pad: float = BOX_PAD_PT,
) -> str:
    ax0, ay0, ax1, ay1 = x0 - pad, y0 - pad, x1 + pad, y1 + pad
    kept = []
    for wx0, wy0, wx1, wy1, text in words:
        cx, cy = (wx0 + wx1) / 2.0, (wy0 + wy1) / 2.0
        if ax0 <= cx <= ax1 and ay0 <= cy <= ay1:
            kept.append(text)
    return " ".join(kept).strip()


_LETTERS = re.compile(r"[A-Za-z]+")


def runs_together(azure_text: str, pdf_text: str) -> bool:
    """Does the clip hold a word so long that the font must be missing its spaces?

    Relative to the service's reading of the same box, so that a genuinely long word
    the paper does use — `hydrodechlorination` — is not mistaken for one.
    """
    long_words = {w for w in _LETTERS.findall(pdf_text or "") if len(w) > MAX_WORD_LETTERS}
    if not long_words:
        return False
    known = set(_LETTERS.findall(azure_text or ""))
    return any(w not in known for w in long_words)


def prefer_embedded(azure_text: str, pdf_text: str) -> tuple[str, str]:
    """The text to use, and why.

    Returns `(text, reason)` where reason is `replaced` or names the refusal, so a
    caller can count what happened instead of assuming it.
    """
    from sentence_reading.llm.debone_quality import glyph_corruption_marks

    azure = (azure_text or "").strip()
    pdf = (pdf_text or "").strip()
    if not pdf:
        # Labels drawn inside a figure, or a scanned page. 3 of 700.
        return azure, "kept_no_embedded"
    if len(azure) < MIN_CHARS_TO_REPLACE:
        return azure, "kept_short"
    if runs_together(azure, pdf):
        return azure, "kept_runs_together"
    # design/345's signatures. When the service's reading carries them, low agreement
    # *is* the corruption, so it must not be read as a reason to keep that reading.
    if not glyph_corruption_marks(azure) and agreement(azure, pdf) < MIN_AGREEMENT:
        return azure, "kept_disagree"
    return pdf, "replaced"
