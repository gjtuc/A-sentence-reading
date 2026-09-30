"""How much history does the account's own pass line need to remember?

The line is the account's average score minus an offset, so the account has to
carry an average. Carrying every word it ever scored is not an option, and the
proposal was a window over the last few practice blocks. Three ways to hold it,
in order of what they cost:

* running sum - a count, a sum and a sum of squares. Three numbers forever, and
  the average is over all of history, so it lags a learner who improves.
* window - the last K word scores. K numbers, forgets on a fixed schedule.
* moving average - one average and one spread, each nudged toward the newest
  word by a fixed weight. Two numbers, forgets smoothly, no history at all.

Whether the forgetting is worth anything depends on whether the score drifts as
the learner practises. Difficulty rose with time in this corpus, so drift has to
be measured inside one tier or it is only difficulty in disguise.

Everything is judged the way the app would have to: for each word in time order,
build the line from the words that came before it only, then judge that word. A
line fitted to the whole corpus at once cannot be compared against that.

    python scripts/running_line_probe.py
"""

from __future__ import annotations

import collections
import json
import math
import pathlib
import re
import statistics as stat

ROWS = pathlib.Path(".cache/human_takes.json")
OUT = pathlib.Path(".cache/running_line.json")
WAY = "sure"
OFFSET = -0.75
WARMUP = 40


def when(stem: str) -> int:
    """The take's own millisecond stamp, so words can be put in time order."""
    found = re.findall(r"_(\d{10,})_", stem)
    return int(found[0]) if found else 0


def ordered(rows: list[dict]) -> list[dict]:
    for r in rows:
        r["at"] = when(r["stem"])
    return sorted(rows, key=lambda r: (r["at"], r["word"]))


def drift(rows: list[dict]) -> dict:
    """Does the score climb with practice once difficulty is held still?"""
    out = {}
    print("  tier  words   first half   second half   change")
    by = collections.defaultdict(list)
    for r in rows:
        if not r["bad"]:
            by[r["tier"]].append(r)
    for t in sorted(by):
        v = sorted(by[t], key=lambda r: r["at"])
        half = len(v) // 2
        a = stat.mean(x[WAY] for x in v[:half])
        b = stat.mean(x[WAY] for x in v[half:])
        out[t] = {"first": a, "second": b, "change": b - a}
        print(f"  {t:>4} {len(v):>6}   {a:>10.3f}   {b:>11.3f}   {b - a:>+6.3f}")
    moves = [out[t]["change"] for t in out]
    print(f"  average change {stat.mean(moves):+.3f},"
          f" rising in {sum(1 for m in moves if m > 0)}/{len(moves)} tiers")
    return out


class Sum:
    """A count, a sum and a sum of squares. Three numbers, never forgets."""

    name = "running sum (3 numbers)"

    def __init__(self) -> None:
        self.n = 0
        self.s = 0.0
        self.q = 0.0

    def ready(self) -> bool:
        return self.n >= WARMUP

    def line(self) -> float:
        avg = self.s / self.n
        var = max(self.q / self.n - avg * avg, 0.0)
        return avg + OFFSET * math.sqrt(var)

    def add(self, v: float) -> None:
        self.n += 1
        self.s += v
        self.q += v * v


class Window:
    """The last K scores. K numbers, forgets on a schedule."""

    def __init__(self, k: int) -> None:
        self.k = k
        self.buf: collections.deque[float] = collections.deque(maxlen=k)
        self.name = f"window of last {k} ({k} numbers)"

    def ready(self) -> bool:
        return len(self.buf) >= WARMUP

    def line(self) -> float:
        return stat.mean(self.buf) + OFFSET * (stat.pstdev(self.buf) or 1e-9)

    def add(self, v: float) -> None:
        self.buf.append(v)


class Moving:
    """One average and one spread, nudged toward each new word. Two numbers."""

    def __init__(self, w: float) -> None:
        self.w = w
        self.avg = None
        self.var = 0.0
        self.n = 0
        self.name = f"moving average w={w} (2 numbers)"

    def ready(self) -> bool:
        return self.n >= WARMUP

    def line(self) -> float:
        return self.avg + OFFSET * math.sqrt(max(self.var, 0.0))

    def add(self, v: float) -> None:
        self.n += 1
        if self.avg is None:
            self.avg = v
            return
        gap = v - self.avg
        self.avg += self.w * gap
        self.var = (1 - self.w) * (self.var + self.w * gap * gap)


def walk(rows: list[dict], make) -> dict:
    """Judge every word from the line the earlier words alone would have set."""
    keep = kept = catch = caught = 0
    held = make()
    for r in rows:
        if held.ready():
            over = r[WAY] >= held.line()
            if r["bad"]:
                catch += 1
                caught += 0 if over else 1
            else:
                keep += 1
                kept += 1 if over else 0
        held.add(r[WAY])
    return {"keep": kept / max(keep, 1), "catch": caught / max(catch, 1),
            "judged": keep + catch}


def cold(rows: list[dict], make) -> None:
    """How far off is the line while the account is still new?"""
    held = make()
    final = None
    marks = [WARMUP, 80, 160, 320, 640, 1280]
    seen = []
    for i, r in enumerate(rows, 1):
        held.add(r[WAY])
        if i in marks and held.ready():
            seen.append((i, held.line()))
        final = held.line() if held.ready() else final
    print(f"  after this many words, the line sits at (settles near {final:.3f})")
    for i, v in seen:
        print(f"    {i:>5} words -> {v:.3f}   off by {v - final:+.3f}")


def main() -> int:
    rows = ordered(json.loads(ROWS.read_text(encoding="utf-8")))
    print(f"{len(rows)} words in time order,"
          f" {len({r['stem'] for r in rows})} takes")

    print("\nDoes the score improve with practice, at a fixed difficulty?")
    moved = drift(rows)

    print(f"\nJudging online with line = average {OFFSET:+} spreads,"
          f" score = {WAY}")
    print("  how the average is held                  keep    catch   judged")
    made = {
        "sum": Sum,
        "win100": lambda: Window(100),
        "win300": lambda: Window(300),
        "win600": lambda: Window(600),
        "ema02": lambda: Moving(0.02),
        "ema01": lambda: Moving(0.01),
        "ema005": lambda: Moving(0.005),
    }
    got = {}
    for key, make in made.items():
        out = walk(rows, make)
        got[key] = out
        print(f"  {make().name:<40} {out['keep']:>5.0%}   {out['catch']:>5.0%}"
              f"   {out['judged']:>6}")

    print("\nCold start, with the running sum")
    cold(rows, Sum)

    OUT.write_text(json.dumps({"drift": moved, "ways": got},
                              ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\nwrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
