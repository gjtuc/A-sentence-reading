"""design/376 - after how many words is an account's own line worth trusting?

`kPassLineWarmup = 40` was never measured. The doc says only "not enough reading
to trust its own line", which is the right reason and an unexamined number.

The question is answerable without any label. An account's line is drawn from its
own average and spread, so early on it is mostly the accident of *which* words
the reader happened to meet. Reading the same words in a different order gives a
different line. That disagreement is the untrustworthiness, and it can be
measured: shuffle the same words into many pseudo-accounts and look at how far
apart their lines sit at each n.

The warm-up should end where the accident stops mattering, that is where the
spread between orderings has fallen to something small next to the line itself.

    python scripts/warmup_probe.py
"""

from __future__ import annotations

import json
import math
import pathlib
import random
import statistics as stat

ROWS = pathlib.Path(".cache/human_takes.json")

# The Dart constants, mirrored. mobile/lib/practice_skill/pass_line.dart
WEIGHT = 0.01
OFFSET = -0.75
FLOOR = 0.45
SHIPPED_WARMUP = 40
COLD = 0.57


def line_after(scores: list[float]) -> float:
    """The account's line after reading `scores`, by the shipped formula."""
    avg = 0.0
    varp = 0.0
    n = 0
    for score in scores:
        n += 1
        if n == 1:
            avg, varp = score, 0.0
            continue
        w = max(WEIGHT, 1.0 / n)
        gap = score - avg
        avg = avg + w * gap
        varp = (1 - w) * (varp + w * gap * gap)
    return max(avg + OFFSET * math.sqrt(max(varp, 0.0)), FLOOR)


def main() -> int:
    rows = json.loads(ROWS.read_text(encoding="utf-8"))
    vals = [float(r["overlap"]) for r in rows if r.get("overlap") is not None]
    print(f"{len(vals)} judged words of real reading")

    final = line_after(vals)
    print(f"the line this reader settles at, all words: {final:.3f}")
    print(f"the cold line a new account starts from:    {COLD:.3f}  (design/375)")

    rng = random.Random(371)
    orders = [rng.sample(vals, len(vals)) for _ in range(400)]
    marks = [5, 10, 20, 30, 40, 60, 80, 120, 200, 300, 500]

    print()
    print("  n   line (median)   spread between orderings   worst gap to settled")
    for n in marks:
        if n > len(vals):
            continue
        lines = [line_after(order[:n]) for order in orders]
        mid = stat.median(lines)
        band = stat.pstdev(lines)
        worst = max(abs(x - final) for x in lines)
        flag = "  <- shipped" if n == SHIPPED_WARMUP else ""
        print(f"{n:4d}      {mid:.3f}            +-{band:.3f}"
              f"                  {worst:.3f}{flag}")

    print()
    # A line that moves by less than this is not worth waiting for: it is smaller
    # than the gap between two neighbouring sounds mattering in a six-sound word.
    for want in (0.05, 0.03, 0.02):
        found = None
        for n in range(2, min(len(vals), 400)):
            lines = [line_after(order[:n]) for order in orders[:120]]
            if stat.pstdev(lines) <= want:
                found = n
                break
        print(f"orderings agree within +-{want:.2f} from n = {found}")

    print()
    print("what the reader is judged by while cold, against what they would be")
    print("judged by with their own line at that point:")
    for n in (10, 20, 40, 80):
        if n > len(vals):
            continue
        lines = [line_after(order[:n]) for order in orders]
        mid = stat.median(lines)
        print(f"  after {n:3d} words   cold {COLD:.3f}   own {mid:.3f}"
              f"   difference {mid - COLD:+.3f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
