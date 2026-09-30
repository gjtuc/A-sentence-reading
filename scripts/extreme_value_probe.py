"""Can the pass line be corrected for word length by extreme value theory?

The minimum certainty of a correctly read word falls from 0.46 at three sounds
to 0.004 at nine, so one line cannot serve both. Extreme value theory offers a
fix: if a word's sounds are independent draws from one distribution, then the
minimum of n draws has a known law, and the line can be moved by n alone.

For n between 3 and 12 the Gumbel limit is not needed. The exact statement is

    P(min of n < t) = 1 - (1 - F(t)) ** n

with F the certainty distribution of a single sound. F can be measured, so the
prediction can be checked against the observed minimum at every length. That is
the whole test, and it stands or falls on independence.

Independence is the doubtful part. A learner who slurs one sound probably slurs
its neighbour, and a reference carrying a sound the word does not own gives a
dead certainty no matter how the word was read. Either one clusters the low
values inside a word, and clustered lows make the real minimum fall faster than
the formula says. So this also counts, for each length, how many words hold two
or more dead sounds against how many the formula expects.

References come from the cache design/371 already built, so nothing is
resynthesized here.

    python scripts/extreme_value_probe.py [--takes 120]
"""

from __future__ import annotations

import collections
import json
import math
import pathlib
import statistics as stat
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "src"))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from sentence_reading.llm.phone_match import _MIN_PHONES, split_phone_units  # noqa: E402
from ctc_prob_score_probe import logprobs, sure_per_word  # noqa: E402
from human_takes_probe import REFS, bare, pcm_of, sidecars  # noqa: E402

import importlib  # noqa: E402

wide = importlib.import_module("timing_spread_probe")

OUT = pathlib.Path(".cache/extreme_value.json")
DEAD = 0.05


def arg(name: str, fallback: int) -> int:
    if name in sys.argv:
        return int(sys.argv[sys.argv.index(name) + 1])
    return fallback


def collect(m, cards, refs) -> list[dict]:
    """Every word of every take, this time keeping each sound's own certainty."""
    rows = []
    clock = time.monotonic()
    for i, card in enumerate(cards, 1):
        sent = (card["expected"] or "").strip()
        ref = refs.get(sent) or []
        if not ref:
            continue
        said = {bare(w) for w in (card.get("heard") or "").split()}
        try:
            pcm, rate = pcm_of(m, card["stem"])
            sheet = logprobs(m, pcm, rate)
        except Exception as exc:  # noqa: BLE001
            print(f"  skip ({type(exc).__name__})")
            continue
        sure = sure_per_word(m, sheet, [list(u) for _w, u in ref])
        for k, (word, raws) in enumerate(ref):
            if len(split_phone_units(" ".join(raws))) < _MIN_PHONES:
                continue
            if sure[k] is None:
                continue
            _cert, _f0, _f1, certs = sure[k]
            rows.append({
                "word": word,
                "n": len(certs),
                "bad": 0 if bare(word) in said else 1,
                "certs": [round(c, 5) for c in certs],
            })
        if i % 20 == 0 or i == len(cards):
            gone = time.monotonic() - clock
            print(f"  {i}/{len(cards)} takes, {len(rows)} words,"
                  f" {gone / i:.1f}s each")
    return rows


def quantile(ranked: list[float], p: float) -> float:
    if not ranked:
        return float("nan")
    at = p * (len(ranked) - 1)
    lo = int(math.floor(at))
    hi = min(lo + 1, len(ranked) - 1)
    return ranked[lo] + (ranked[hi] - ranked[lo]) * (at - lo)


def cdf_at(ranked: list[float], t: float) -> float:
    """Share of single sounds under t."""
    import bisect

    return bisect.bisect_right(ranked, t) / len(ranked)


def invert(ranked: list[float], want: float) -> float:
    """The t with that share of sounds under it."""
    return quantile(ranked, max(0.0, min(1.0, want)))


def main() -> int:
    cards = sidecars()
    if not REFS.exists():
        print("no reference cache; run human_takes_probe.py first")
        return 1
    refs = json.loads(REFS.read_text(encoding="utf-8"))
    take = arg("--takes", 120)
    cards = cards[:: max(1, len(cards) // take)][:take]
    print(f"{len(cards)} takes sampled across the corpus")

    m = wide.M()
    rows = collect(m, cards, refs)
    OUT.write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")
    good = [r for r in rows if not r["bad"]]
    print(f"\n{len(rows)} words, {len(good)} the transcript confirms")

    pool = sorted(c for r in good for c in r["certs"])
    print(f"one sound's certainty, pooled over {len(pool)} sounds of"
          f" correctly read words")
    for p in (0.01, 0.05, 0.10, 0.25, 0.50, 0.75):
        print(f"  bottom {p:>4.0%} of sounds sit under {quantile(pool, p):.4f}")
    print(f"  share of sounds under {DEAD} (call it dead):"
          f" {cdf_at(pool, DEAD):.1%}")

    by = collections.defaultdict(list)
    for r in good:
        by[r["n"]].append(r)

    print("\nDoes the exact order statistic predict the observed minimum?")
    print("  the formula assumes a word's sounds are independent draws")
    print("  n   words   observed median min   predicted   observed 10%   pred")
    table = {}
    for n in sorted(by):
        group = by[n]
        if len(group) < 25:
            continue
        mins = sorted(min(r["certs"]) for r in group)
        row = {"words": len(group)}
        for tag, p in (("med", 0.50), ("p10", 0.10)):
            seen = quantile(mins, p)
            # P(min < t) = p  ->  F(t) = 1 - (1 - p) ** (1 / n)
            pred = invert(pool, 1.0 - (1.0 - p) ** (1.0 / n))
            row[tag] = seen
            row[f"{tag}_pred"] = pred
        table[n] = row
        print(f"  {n:>2} {len(group):>6}   {row['med']:>17.4f}"
              f"   {row['med_pred']:>9.4f}   {row['p10']:>12.4f}"
              f"   {row['p10_pred']:>6.4f}")

    print("\nAre the low sounds independent, or do they clump in one word?")
    print("  a dead sound is under", DEAD)
    print("  n   words   words with 2+ dead   the formula expects")
    p_dead = cdf_at(pool, DEAD)
    clump = {}
    for n in sorted(table):
        group = by[n]
        seen = sum(1 for r in group if sum(1 for c in r["certs"] if c < DEAD) >= 2)
        # under independence: 1 - P(0 dead) - P(exactly 1 dead)
        q = 1.0 - p_dead
        want = 1.0 - q ** n - n * p_dead * q ** (n - 1)
        clump[n] = {"seen": seen, "want": want * len(group)}
        print(f"  {n:>2} {len(group):>6}   {seen:>17}   {want * len(group):>18.1f}")

    print("\nHow far is the length effect from a pure log n shift?")
    print("  n   log(median min)   if it were log n")
    base = None
    for n in sorted(table):
        v = table[n]["med"]
        if v <= 0:
            continue
        if base is None:
            base, n0 = math.log(v), n
        print(f"  {n:>2}   {math.log(v):>15.3f}"
              f"   {base - math.log(n / n0) / 1.0:>16.3f}")

    pathlib.Path(".cache/extreme_value_report.json").write_text(
        json.dumps({"by_n": table, "clump": clump, "p_dead": p_dead},
                   ensure_ascii=False, indent=1),
        encoding="utf-8",
    )
    print("\nwrote .cache/extreme_value_report.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
