"""design/379 - why does another correct native reading score 0.96 and not 1.00?

Matching a reference against the reading it was cut from gives 1.000. Matching it
against a *different* correct reading gives 0.92 to 0.97. That remaining gap is the
headroom the scoring actually has, so it is worth knowing what it is made of.

This aligns each word against the best-matching stretch of the other voice's
reading and names every disagreement: whether a sound was swapped, added or
dropped, whether the swap was vowel for vowel or vowel for consonant, whether a
schwa was involved, and whether it happened at the edge of the word or inside it.

Symbols print as escaped codepoints -- a Windows console cannot render IPA.

Usage:
    python scripts/voice_gap_probe.py .cache/ev416.jsonl 5
"""
from __future__ import annotations

import collections
import json
import pathlib
import sys
from xml.sax.saxutils import escape

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from sentence_reading.llm import sound_reference as sr  # noqa: E402
from sentence_reading.llm.phone_match import split_phone_units  # noqa: E402

MIN_UNITS = 3

# Enough to tell a vowel from a consonant in this model's alphabet. Anything not
# here counts as a consonant, which is the safe way round: a missed vowel shows up
# as a consonant swap and understates the vowel story rather than inventing one.
VOWELS = set("aeiouy") | set(
    "\u0251\u0252\u0254\u0259\u025b\u025c\u025e\u0264\u0268\u026a"
    "\u0275\u0276\u0279\u0289\u028a\u028c\u028f\u0250\u00e6\u00f8"
)
SCHWA = "\u0259"

VOICES = [
    ("same voice, slower", "en-US-Neural2-D", "0.8"),
    ("another US male", "en-US-Neural2-A", None),
    ("a US female", "en-US-Neural2-F", None),
    ("a British voice", "en-GB-Neural2-B", None),
]


def esc(sym: str) -> str:
    return sym.encode("unicode_escape").decode("ascii") if sym else "-"


def rows(path: pathlib.Path) -> list[dict]:
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            pass
    return out


def reading_of(text: str, voice: str, rate: str | None) -> list[str]:
    from sentence_reading.llm.hear_waveform import phone_frames

    body = escape(text)
    ssml = (
        f"<speak><prosody rate='{rate}'>{body}</prosody></speak>"
        if rate
        else f"<speak>{body}</speak>"
    )
    raw, _t = sr.synth_marked(ssml, voice)
    pcm, _rate = sr.pcm_of(raw)
    return split_phone_units(
        " ".join(str(one["sym"]) for one in phone_frames(pcm))
    )


def align(left: list[str], right: list[str]) -> list[tuple[str, str, str]]:
    """Cheapest edit script turning `left` into `right`, as (op, a, b)."""
    n, m = len(left), len(right)
    cost = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(n + 1):
        cost[i][0] = i
    for j in range(m + 1):
        cost[0][j] = j
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            same = left[i - 1] == right[j - 1]
            cost[i][j] = min(
                cost[i - 1][j - 1] + (0 if same else 1),
                cost[i - 1][j] + 1,
                cost[i][j - 1] + 1,
            )
    out: list[tuple[str, str, str]] = []
    i, j = n, m
    while i > 0 or j > 0:
        if i and j and cost[i][j] == cost[i - 1][j - 1] + (
            0 if left[i - 1] == right[j - 1] else 1
        ):
            op = "same" if left[i - 1] == right[j - 1] else "swap"
            out.append((op, left[i - 1], right[j - 1]))
            i, j = i - 1, j - 1
        elif i and cost[i][j] == cost[i - 1][j] + 1:
            out.append(("dropped", left[i - 1], ""))
            i -= 1
        else:
            out.append(("added", "", right[j - 1]))
            j -= 1
    out.reverse()
    return out


def best_window(ref: list[str], run: list[str]) -> list[str]:
    """The stretch of `run` the scorer would have matched this word against."""
    span = len(ref)
    best, score = [], -1.0
    for width in range(max(1, span - 1), span + 3):
        for start in range(0, max(1, len(run) - width + 1)):
            cut = run[start : start + width]
            ops = align(ref, cut)
            wrong = sum(1 for op, _a, _b in ops if op != "same")
            got = 1.0 - wrong / max(len(ref), len(cut))
            if got > score:
                score, best = got, cut
    return best


def kind_of(a: str, b: str) -> str:
    av = a and a[0] in VOWELS
    bv = b and b[0] in VOWELS
    if a == SCHWA or b == SCHWA:
        return "schwa for a full vowel" if (av and bv) else "schwa for a consonant"
    if av and bv:
        return "vowel for another vowel"
    if (not av) and (not bv):
        return "consonant for another consonant"
    return "vowel for a consonant"


def main() -> int:
    src = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else ".cache/ev416.jsonl")
    want = int(sys.argv[2]) if len(sys.argv) > 2 else 5
    takes = [
        r
        for r in rows(src)
        if r.get("kind") == "practice_skill_align"
        and (r.get("details") or {}).get("phase") == "align"
    ]
    takes.sort(key=lambda r: str(r.get("ts") or ""))
    d = takes[want - 1].get("details") or {}

    text = str(d.get("spoken_line") or "").strip()
    words = [w.strip() for w in str(d.get("slot_pieces") or "").split("|")]
    refs = [
        split_phone_units(w.strip())
        for w in str(d.get("target_phones") or "").split("|")
    ]
    pairs = [(w, r) for w, r in zip(words, refs) if len(r) >= MIN_UNITS]

    for name, voice, rate in VOICES:
        run = reading_of(text, voice, rate)
        ops: collections.Counter[str] = collections.Counter()
        where: collections.Counter[str] = collections.Counter()
        swaps: collections.Counter[tuple[str, str]] = collections.Counter()
        sounds = wrong = 0
        perfect = 0
        for _w, ref in pairs:
            cut = best_window(ref, run)
            script = align(ref, cut)
            bad = [x for x in script if x[0] != "same"]
            sounds += len(ref)
            wrong += len(bad)
            if not bad:
                perfect += 1
            for idx, (op, a, b) in enumerate(script):
                if op == "same":
                    continue
                ops[op if op != "swap" else kind_of(a, b)] += 1
                edge = idx == 0 or idx >= len(script) - 1
                where["at the edge of the word" if edge else "inside the word"] += 1
                if op == "swap":
                    swaps[(a, b)] += 1

        print(f"== {name}")
        print(f"   {perfect}/{len(pairs)} words matched exactly; "
              f"{wrong} of {sounds} sounds disagreed ({100 * wrong // sounds}%)")
        for kind, n in ops.most_common():
            print(f"     {kind:32s} {n:3d}")
        for place, n in where.most_common():
            print(f"     {place:32s} {n:3d}")
        top = swaps.most_common(4)
        if top:
            shown = ", ".join(f"{esc(a)}->{esc(b)} x{n}" for (a, b), n in top)
            print(f"     most repeated swaps: {shown}")
        print()

    print("reading: a swap is two correct readings saying the same syllable")
    print("differently. A drop or an add is one reading having a sound the other")
    print("does not, which is what a boundary that moved looks like.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
