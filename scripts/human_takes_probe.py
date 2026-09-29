"""Re-score the recorded human takes with the design/371 rules.

Everything so far was measured on synthetic readings, where a wrong word was
made by swapping in a near miss. That proves the scorer can tell two machine
voices apart. It does not prove anything about a person reading fast.

The corpus is the ten sample rounds: 619 takes, 481 of them carrying the text
that was on screen. Difficulty is recorded on every take as `skill_tier` 0..9,
which is the reading speed the learner was asked to keep up with, so the same
data answers whether the pass line has to move with difficulty.

Labels come from the take itself, not from a human pass:

* right - the word appears in the take's own transcript, so the speaker
  demonstrably said it.
* wrong - the word was on screen and is missing from the transcript, so the
  speaker most likely did not say it cleanly.

That label is noisy in both directions, but it is a real person's real mistake
rather than a swap chosen by this script, and it comes from a signal the score
never sees. Agreement between the two is therefore worth something.

References are built once per distinct sentence and cached, because 481 takes
share only 128 sentences.

    python scripts/human_takes_probe.py            # resume, uses the cache
    python scripts/human_takes_probe.py --fresh    # rebuild the references
"""

from __future__ import annotations

import collections
import json
import pathlib
import re
import statistics as stat
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "src"))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from sentence_reading.llm.phone_match import (  # noqa: E402
    _MIN_PHONES,
    best_window_overlap,
    split_phone_units,
)
from ctc_reference_probe import pcm_from_wav  # noqa: E402
from cross_voice_probe import REF_VOICE, synth_voice  # noqa: E402
from halfgap_tile_probe import hand_out  # noqa: E402
from two_voices_probe import cut_flat, cut_own, ssml_broken  # noqa: E402
from ctc_prob_score_probe import logprobs, sure_per_word  # noqa: E402

import importlib  # noqa: E402

wide = importlib.import_module("timing_spread_probe")

TAKES = pathlib.Path(".cache/takes")
REFS = pathlib.Path(".cache/human_refs_tokens.json")
OUT = pathlib.Path(".cache/human_takes.json")
BREAK = 100
PAD = 25

# Every run of non-space characters, not only the letters. The broken-up reading
# used to be rebuilt out of letter words alone while the natural reading said the
# whole line, so the sounds of `(111)` and `2 theta = 43.6` had no slot of their
# own and were forced onto whichever word would take them. One sentence handed
# the word `The` seventy sounds.
_TOKEN = re.compile(r"\S+")


def units(syms) -> list[str]:
    return split_phone_units(" ".join(syms))


def bare(word: str) -> str:
    return word.strip(".,;:()[]\"'").lower()


def ssml_every(sentence: str, ms: int) -> tuple[str, list[str]]:
    """A mark around every token the voice will read, numbers included."""
    from xml.sax.saxutils import escape

    tokens = _TOKEN.findall(sentence)
    parts = ["<speak>"]
    for i, token in enumerate(tokens):
        parts.append(
            f'<mark name="w{i}"/>{escape(token)}<mark name="e{i}"/>'
            f'<break time="{ms}ms"/> '
        )
    parts.append("</speak>")
    return "".join(parts), tokens


def cut_tokens(m, heard, tokens, times, rate, pad_ms, total):
    """Each token's own window. A token the voice says nothing for gets nothing."""
    pad = pad_ms / 1000.0
    out = []
    for i, token in enumerate(tokens):
        start = times.get(f"w{i}")
        if start is None:
            out.append((token, []))
            continue
        # A closing mark can collapse into the next opening one. Fall back to
        # where the next token starts, not to the end of the line.
        stop = times.get(f"e{i}")
        if stop is None:
            stop = min(
                (times[f"w{j}"] for j in range(i + 1, len(tokens))
                 if f"w{j}" in times),
                default=total,
            )
        lo, hi = start - pad, stop + pad
        out.append((token, [
            s["sym"] for s in heard
            if lo <= (m.s(s["f0"], rate) + m.s(s["f1"], rate)) / 2 < hi
        ]))
    return out


def hand_out_loose(refs: list[list[str]], take: list[str]) -> list[list[str]]:
    """Give sounds to tokens in order, and let a sound go to nobody.

    `hand_out` has to place every sound, which is right when both readings say
    the same thing. Here the natural reading holds sounds no token owns, and
    forcing those onto a neighbour is what bloated the references.
    """
    from sentence_reading.llm.phone_match import overlap_ratio

    n, wide_n = len(refs), len(take)
    neg = float("-inf")
    best = [[neg] * (wide_n + 1) for _ in range(n + 1)]
    back: list[list[tuple[str, int] | None]] = [
        [None] * (wide_n + 1) for _ in range(n + 1)
    ]
    for j in range(wide_n + 1):
        best[0][j] = 0.0
        back[0][j] = ("skip", j - 1) if j else None
    for i in range(1, n + 1):
        ref = refs[i - 1]
        widest = len(ref) + 2 if ref else 0
        for j in range(wide_n + 1):
            if j and best[i][j - 1] > best[i][j]:
                best[i][j] = best[i][j - 1]
                back[i][j] = ("skip", j - 1)
            for width in range(0, min(widest, j) + 1):
                k = j - width
                if best[i - 1][k] == neg:
                    continue
                got = best[i - 1][k]
                if width:
                    got += overlap_ratio(ref, take[k:j])
                if got > best[i][j]:
                    best[i][j] = got
                    back[i][j] = ("take", k)
    out: list[list[str]] = [[] for _ in range(n)]
    i, j = n, wide_n
    while i > 0:
        move = back[i][j]
        if move is None:
            break
        kind, k = move
        if kind == "skip":
            j = k
        else:
            out[i - 1] = take[k:j]
            i, j = i - 1, k
    return out


def sidecars() -> list[dict]:
    """Every take that carries the text the learner was reading."""
    out = []
    for path in sorted(TAKES.glob("*.json")):
        one = json.loads(path.read_text(encoding="utf-8"))
        if not (one.get("expected") or "").strip():
            continue
        if not (TAKES / f"{one['stem']}.m4a").exists():
            continue
        out.append(one)
    return out


def build_refs(m, sents: list[str]) -> dict[str, list]:
    """One reference per sentence: clean words picked out of the natural run."""
    cache = {}
    if REFS.exists() and "--fresh" not in sys.argv:
        cache = json.loads(REFS.read_text(encoding="utf-8"))
    todo = [s for s in sents if s not in cache]
    print(f"references: {len(cache)} cached, {len(todo)} to build")
    for n, sent in enumerate(todo, 1):
        try:
            flat_raw, times0 = synth_voice(f"<speak>{sent}</speak>", REF_VOICE)
            pcm0, rate0 = pcm_from_wav(flat_raw)
            heard0 = m.run(pcm0, rate0)
            ssml, words = ssml_every(sent, BREAK)
            raw, times = synth_voice(ssml, REF_VOICE)
            pcm, rate = pcm_from_wav(raw)
            clean = cut_tokens(
                m, m.run(pcm, rate), words, times, rate, PAD, len(pcm) / rate
            )
            natural_run = [s["sym"] for s in heard0]
            given = hand_out_loose([list(u) for _w, u in clean], natural_run)
            cache[sent] = [[w, given[i]] for i, (w, _u) in enumerate(clean)]
        except Exception as exc:  # noqa: BLE001
            print(f"  skip ({type(exc).__name__}) {sent[:40]}")
            cache[sent] = []
        if n % 10 == 0 or n == len(todo):
            REFS.write_text(
                json.dumps(cache, ensure_ascii=False), encoding="utf-8"
            )
            print(f"  built {n}/{len(todo)}")
    REFS.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
    return cache


def pcm_of(m, stem: str):
    """The take's own recording, decoded the way the server decodes it."""
    from sentence_reading.llm.hear_waveform import _pcm16k

    data = (TAKES / f"{stem}.m4a").read_bytes()
    return _pcm16k(data), 16000


def main() -> int:
    cards = sidecars()
    print(f"{len(cards)} takes carry the text they were reading")
    m = wide.M()
    refs = build_refs(m, sorted({(c["expected"]).strip() for c in cards}))

    rows = []
    clock = time.monotonic()
    for n, card in enumerate(cards, 1):
        sent = card["expected"].strip()
        ref = refs.get(sent) or []
        if not ref:
            continue
        said = set(bare(w) for w in (card.get("heard") or "").split())
        try:
            pcm, rate = pcm_of(m, card["stem"])
            sheet = logprobs(m, pcm, rate)
            heard = m.run(pcm, rate)
        except Exception as exc:  # noqa: BLE001
            print(f"  skip take ({type(exc).__name__}) {card['stem'][:20]}")
            continue
        run = units(s["sym"] for s in heard)
        sure = sure_per_word(m, sheet, [list(u) for _w, u in ref])
        for i, (word, raws) in enumerate(ref):
            piece = units(raws)
            if len(piece) < _MIN_PHONES or sure[i] is None:
                continue
            cert, f0, f1, certs = sure[i]
            here = [
                s for s in heard if f0 <= (s["f0"] + s["f1"]) / 2 < f1
            ]
            extra = max(0, len(here) - len(certs))
            rows.append(
                {
                    "tier": card["skill_tier"],
                    "rate": card.get("tts_rate"),
                    "round": card.get("round"),
                    "stem": card["stem"],
                    "word": word,
                    "n": len(certs),
                    "bad": 0 if bare(word) in said else 1,
                    "overlap": best_window_overlap(piece, run),
                    "sure": cert,
                    "worst": min(certs),
                    "full": cert - extra / len(certs),
                    "extra": extra,
                }
            )
        if n % 25 == 0 or n == len(cards):
            gone = time.monotonic() - clock
            print(f"  scored {n}/{len(cards)} takes, {len(rows)} words,"
                  f" {gone / n:.2f}s per take")
            OUT.write_text(
                json.dumps(rows, ensure_ascii=False), encoding="utf-8"
            )

    OUT.write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")
    report(rows)
    print(f"\nwrote {OUT}")
    return 0


def keep_line(vals: list[float], keep: float = 0.90) -> float:
    if not vals:
        return 0.0
    ranked = sorted(vals)
    at = int(round((1.0 - keep) * (len(ranked) - 1)))
    return ranked[max(0, min(at, len(ranked) - 1))]


def report(rows: list[dict]) -> None:
    good = [r for r in rows if not r["bad"]]
    bad = [r for r in rows if r["bad"]]
    print(f"\n{len(rows)} words: {len(good)} the transcript confirms,"
          f" {len(bad)} it does not")

    print("\none line for everybody, set to keep 90% of confirmed words")
    for way in ("overlap", "full", "worst"):
        line = keep_line([r[way] for r in good])
        caught = sum(1 for r in bad if r[way] < line)
        print(f"  {way:<8} line {line:.3f}  catches {caught}/{len(bad)}"
              f" {caught / max(1, len(bad)):.0%}")

    print("\nby difficulty, one line for everybody (full score)")
    line = keep_line([r["full"] for r in good])
    print(f"  shared line {line:.3f}")
    print("  tier  words   confirmed avg   not-confirmed avg   kept   caught")
    by = collections.defaultdict(lambda: {"g": [], "b": []})
    for r in rows:
        by[r["tier"]]["b" if r["bad"] else "g"].append(r)
    for tier in sorted(by):
        g, b = by[tier]["g"], by[tier]["b"]
        gm = stat.mean(x["full"] for x in g) if g else float("nan")
        bm = stat.mean(x["full"] for x in b) if b else float("nan")
        kept = sum(1 for x in g if x["full"] >= line)
        hit = sum(1 for x in b if x["full"] < line)
        print(f"  {tier:>4}  {len(g) + len(b):>5}   {gm:>13.3f}   {bm:>17.3f}"
              f"   {kept}/{len(g)}   {hit}/{len(b)}")

    print("\nby difficulty, its own line set to keep 90% of that tier")
    print("  tier   own line   catches")
    for tier in sorted(by):
        g, b = by[tier]["g"], by[tier]["b"]
        own = keep_line([x["full"] for x in g])
        hit = sum(1 for x in b if x["full"] < own)
        print(f"  {tier:>4}   {own:>8.3f}   {hit}/{len(b)}"
              f" {hit / max(1, len(b)):.0%}")


if __name__ == "__main__":
    raise SystemExit(main())
