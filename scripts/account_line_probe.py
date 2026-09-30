"""A pass line the account calibrates itself, held against the measured spread.

The idea under test: keep, per account, the average minimum for each block of
word length, then pass a word that beats its block average by an offset the
difficulty chooses. Nothing needs labelling and the length effect cancels, so it
is the first proposal here that could ship as it stands.

Three things decide whether it works, and all three are measurable on the 619
recorded takes:

* the average has to be computable without labels, so it must be taken over
  every reading the account made, bad ones included
* the difficulty offset has to correspond to a real shift in the score
* the spread inside a block has to be small next to the offset, or no offset
  separates anything

The third is where it is decided. A block whose spread is as wide as its own
average cannot be split by moving the centre.

    python scripts/account_line_probe.py
"""

from __future__ import annotations

import bisect
import collections
import json
import pathlib
import statistics as stat

ROWS = pathlib.Path(".cache/human_takes.json")
OUT = pathlib.Path(".cache/account_line.json")
WAYS = ("worst", "sure", "full")


def block(row: dict) -> int:
    return min(max(row["n"], 2), 10)


def auc(good: list[dict], bad: list[dict], key) -> float:
    """Chance that a confirmed word outscores an unconfirmed one."""
    ranked = sorted(key(r) for r in good)
    total = 0.0
    for value in (key(r) for r in bad):
        lo = bisect.bisect_left(ranked, value)
        hi = bisect.bisect_right(ranked, value)
        total += lo + (hi - lo) * 0.5
    return 1.0 - total / (len(ranked) * len(bad))


def centre(rows: list[dict], way: str) -> tuple[dict, dict]:
    """What the account would store: one average and spread per block."""
    avg, sd = {}, {}
    by = collections.defaultdict(list)
    for r in rows:
        by[block(r)].append(r[way])
    for k, v in by.items():
        avg[k] = stat.mean(v)
        sd[k] = stat.pstdev(v) or 1e-9
    return avg, sd


def main() -> int:
    rows = json.loads(ROWS.read_text(encoding="utf-8"))
    good = [r for r in rows if not r["bad"]]
    bad = [r for r in rows if r["bad"]]
    print(f"{len(rows)} words: {len(good)} the transcript confirms, {len(bad)} not")

    report: dict = {"ways": {}}
    for way in WAYS:
        # No labels exist in the app, so the centre comes from every reading.
        avg, sd = centre(rows, way)
        print(f"\n=== {way}   AUC {auc(good, bad, lambda r: r[way]):.4f}")
        print("  is the score flat across word length?")
        print("  block  words   avg     spread   spread/avg")
        by = collections.defaultdict(list)
        for r in good:
            by[block(r)].append(r[way])
        flat = {}
        for k in sorted(by):
            v = by[k]
            mean, spread = stat.mean(v), stat.pstdev(v)
            flat[k] = {"avg": mean, "sd": spread,
                       "rel": spread / max(abs(mean), 1e-9), "words": len(v)}
            print(f"  {k:>5}{'+' if k == 10 else ' '} {len(v):>6}  {mean:>6.3f}"
                  f"  {spread:>7.3f}   {spread / max(abs(mean), 1e-9):>9.2f}")
        wide = max(flat[k]["rel"] for k in flat)
        print(f"  widest spread next to its own average: {wide:.2f}"
              f"  ({'too wide to split' if wide > 0.5 else 'usable'})")

        print("  line = block average + k * block spread")
        print("    k     keep confirmed     catch unconfirmed")
        offsets = {}
        for k in (-1.0, -0.75, -0.5, -0.25, 0.0, 0.25):
            def over(r, k=k):
                return r[way] >= avg[block(r)] + k * sd[block(r)]
            kept = sum(1 for r in good if over(r))
            caught = sum(1 for r in bad if not over(r))
            offsets[k] = {"keep": kept / len(good), "catch": caught / len(bad)}
            print(f"  {k:>+5.2f}  {kept:>5}/{len(good)} {kept / len(good):>4.0%}"
                  f"        {caught:>4}/{len(bad)} {caught / len(bad):>4.0%}")

        # Does difficulty move the score, and which way? If it already falls,
        # raising the bar with difficulty punishes twice.
        print("  difficulty, at a fixed line of the block average")
        print("  tier  words   avg     shift in spreads   kept")
        tiers = {}
        bt = collections.defaultdict(list)
        for r in good:
            bt[r["tier"]].append(r)
        for t in sorted(bt):
            v = bt[t]
            here = stat.mean(x[way] for x in v)
            shift = stat.mean(
                (x[way] - avg[block(x)]) / sd[block(x)] for x in v
            )
            kept = sum(1 for x in v if x[way] >= avg[block(x)])
            tiers[t] = {"avg": here, "shift": shift, "keep": kept / len(v)}
            print(f"  {t:>4} {len(v):>6}  {here:>6.3f}  {shift:>+16.3f}"
                  f"   {kept / len(v):>4.0%}")
        span = tiers[min(tiers)]["shift"] - tiers[max(tiers)]["shift"]
        print(f"  tier 0 sits {span:+.2f} spreads above tier"
              f" {max(tiers)}; a bar that rises with difficulty adds to this")
        report["ways"][way] = {"flat": flat, "offsets": offsets,
                               "tiers": tiers, "tier_span": span}

    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=1),
                   encoding="utf-8")
    print(f"\nwrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
