"""design/382 - the owner's symmetric score on 619 real recordings.

`symmetric_score_probe.py` showed the formula fixes `loss` read as `lost` on
synthesised audio. Synthesised audio is clean: the model said exactly as many
sounds as the reference had, every time. On a person reading fast it will not, and
a divisor that grows with every sound the model imagines would quietly punish
correct reading.

`.cache/human_takes.json` already holds, per word, the reference sound count, the
certainty of each sound, and how many sounds the model read off the audio inside
that word -- so the formula can be compared on real recordings without running the
model again.

Labels are the take's own transcript and are noisy. They are used only to report
keep and catch at a matched operating point, never to pick a line. Every method is
pinned to keep the same share of correctly-read words, which is the only honest way
to compare two different scales.

Usage:
    python scripts/symmetric_human_probe.py
"""
from __future__ import annotations

import collections
import json
import pathlib
import statistics as stat
import sys

ROWS = pathlib.Path(".cache/human_takes_wide.json")
NARROW = pathlib.Path(".cache/human_takes.json")


def keep_line(vals: list[float], keep: float = 0.90) -> float:
    """The line that leaves `keep` of these values above it."""
    if not vals:
        return 0.0
    ranked = sorted(vals)
    at = int(round((1.0 - keep) * (len(ranked) - 1)))
    return ranked[max(0, min(at, len(ranked) - 1))]


def auc(good: list[float], bad: list[float]) -> float:
    """Chance that a correctly-read word outranks a wrongly-read one."""
    if not good or not bad:
        return float("nan")
    ranked = sorted((v, 0) for v in good)
    ranked += sorted((v, 1) for v in bad)
    ranked.sort()
    wins = ties = 0
    seen = 0
    i = 0
    while i < len(ranked):
        j = i
        while j < len(ranked) and ranked[j][0] == ranked[i][0]:
            j += 1
        here_bad = sum(1 for k in range(i, j) if ranked[k][1] == 1)
        here_good = (j - i) - here_bad
        wins += here_good * seen
        ties += here_good * here_bad
        seen += here_bad
        i = j
    return (wins + 0.5 * ties) / (len(good) * len(bad))


def main() -> int:
    if not ROWS.exists():
        print(f"no {ROWS} -- run scripts/human_takes_probe.py first")
        return 1
    rows = json.loads(ROWS.read_text(encoding="utf-8"))
    print(f"{len(rows)} judged words from {len({r['stem'] for r in rows})} "
          f"recordings")

    # The owner's score: every reference sound worth up to 1, divided by the
    # longer of the reference and what the reader actually said.
    for r in rows:
        n = max(1, int(r["n"]))
        tight = max(0, int(r.get("extra") or 0))
        broad = max(0, int(r.get("extra_wide") or tight))
        # The narrow count stops at the reference's last sound; the wide one runs
        # to where the next word begins, so it can see a sound the reader added
        # after the reference ran out.
        r["owner_tight"] = r["sure"] * n / (n + tight)
        r["owner"] = r["sure"] * n / (n + broad)
        r["extra"] = broad

    spread = collections.Counter(min(5, int(r.get("extra") or 0)) for r in rows)
    print()
    print("sounds the model read off the audio beyond the reference's own count")
    print("(this is what the owner's divisor grows by, so it decides everything)")
    for k in sorted(spread):
        label = f"{k}" if k < 5 else "5 or more"
        print(f"  {label:>9} extra  {spread[k]:>5}  {spread[k]/len(rows):>6.1%}")
    withextra = [r for r in rows if (r.get("extra") or 0) > 0]
    print(f"  words with any extra sound: {len(withextra)}/{len(rows)} "
          f"{len(withextra)/len(rows):.1%}")

    good = [r for r in rows if not r["bad"]]
    bad = [r for r in rows if r["bad"]]
    print()
    print(f"{len(good)} words the transcript confirms, {len(bad)} it does not")
    print()
    print("every method pinned to keep 90% of the confirmed words")
    print("  method     line     catches          AUC")
    order = [
        ("overlap", "shipped rule (hard match, max divisor)"),
        ("sure", "mean certainty (design/381)"),
        ("worst", "least certain sound alone"),
        ("full", "mean minus extra sounds (design/371)"),
        ("owner_tight", "owner's score, narrow window"),
        ("owner", "owner's symmetric score, window to the next word"),
    ]
    for key, _label in order:
        line = keep_line([r[key] for r in good])
        caught = sum(1 for r in bad if r[key] < line)
        kept = sum(1 for r in good if r[key] >= line)
        print(f"  {key:<9} {line:>6.3f}   {caught:>3}/{len(bad)} "
              f"{caught/max(1,len(bad)):>4.0%}   kept {kept/len(good):>4.0%}"
              f"   {auc([r[key] for r in good], [r[key] for r in bad]):.3f}")
    print()
    for key, label in order:
        print(f"  {key:<9} {label}")

    print()
    print("the words where the divisor actually moved "
          f"({len(withextra)} of them)")
    g2 = [r for r in withextra if not r["bad"]]
    b2 = [r for r in withextra if r["bad"]]
    if g2 and b2:
        for key in ("sure", "owner"):
            print(f"  {key:<9} confirmed {stat.mean(r[key] for r in g2):.3f}"
                  f"   not confirmed {stat.mean(r[key] for r in b2):.3f}"
                  f"   AUC {auc([r[key] for r in g2], [r[key] for r in b2]):.3f}")
    print()
    print("two parts together, still pinned to keep 90% of confirmed words")
    print("a word fails if its score is under the line OR one sound is under")
    print("the floor. The floor eats some of the keep, so the line moves up to")
    print("give it back -- that is what makes this a fair comparison.")
    print("  score   floor    line    catches")
    for key in ("sure", "owner", "owner_tight", "overlap"):
        for floor in (0.0, 0.0005, 0.002, 0.01, 0.05):
            left = [r for r in good if r["worst"] >= floor]
            if len(left) < 0.90 * len(good):
                print(f"  {key:<7} {floor:<7.4f}  the floor alone drops more "
                      f"than 10% of confirmed words")
                continue
            # Keep 90% of all confirmed words between the two tests together.
            want = int(round(0.90 * len(good)))
            line = keep_line([r[key] for r in left],
                             keep=want / max(1, len(left)))
            kept = sum(1 for r in good
                       if r["worst"] >= floor and r[key] >= line)
            caught = sum(1 for r in bad
                         if r["worst"] < floor or r[key] < line)
            print(f"  {key:<7} {floor:<7.4f} {line:>6.3f}   {caught:>3}/{len(bad)}"
                  f" {caught/len(bad):>4.0%}   kept {kept/len(good):>4.0%}")

    print()
    print("how much an added sound should cost -- full point, part point, capped")
    print("(the owner asked whether a sound that only slightly misses should")
    print(" count as a whole point in the divisor, or only a fraction)")
    print("  cost per added sound   line    catches        AUC")
    for weight, cap, label in ((1.0, 99, "a whole point each"),
                               (0.5, 99, "half a point each"),
                               (0.25, 99, "a quarter each"),
                               (1.0, 1, "a whole point, at most 1"),
                               (1.0, 2, "a whole point, at most 2"),
                               (1.0, 3, "a whole point, at most 3")):
        vals = {}
        for r in rows:
            n = max(1, int(r["n"]))
            add = weight * min(cap, max(0, int(r["extra"])))
            vals[id(r)] = r["sure"] * n / (n + add)
        g = [vals[id(r)] for r in good]
        b = [vals[id(r)] for r in bad]
        line = keep_line(g)
        caught = sum(1 for v in b if v < line)
        lost = stat.mean(r["sure"] - vals[id(r)] for r in good)
        print(f"  {label:<22} {line:>6.3f}   {caught:>3}/{len(bad)} "
              f"{caught/len(bad):>4.0%}   {auc(g, b):.3f}   costs a right "
              f"word {lost:.3f}")

    print()
    print("what the divisor costs a correctly-read word")
    drop = [r["sure"] - r["owner"] for r in good]
    print(f"  average loss {stat.mean(drop):.3f}, worst {max(drop):.3f}")
    hurt = sum(1 for d in drop if d > 0.1)
    print(f"  confirmed words losing more than 0.100: {hurt}/{len(good)} "
          f"{hurt/len(good):.1%}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
