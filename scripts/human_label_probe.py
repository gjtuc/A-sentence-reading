"""Re-read the human-take labels, then measure again.

`human_takes_probe.py` calls a word "said" when it appears in the take's own
transcript. That label is free and it comes from a signal the score never sees,
which is why it is worth using, but it is broken in ways that are easy to see
once the misses are listed: `x-ray` arrives as one transcript token while the
printed sentence has `X` and `ray`, and the transcript spells `vapour` the
American way. Those two alone account for 77 of the 673 words the first pass
called unsaid, every one of them scoring above 0.85.

Grading a scorer against a broken label understates it, so this rebuilds the
label with hyphen pieces and the common British spellings allowed, and reports
what changes. It reads the saved scores, so nothing is re-heard.
"""

from __future__ import annotations

import bisect
import collections
import json
import pathlib
import re
import statistics as stat

TAKES = pathlib.Path(".cache/takes")
SCORED = pathlib.Path(".cache/human_takes.json")
OUT = pathlib.Path(".cache/human_label.json")
WAYS = ("overlap", "sure", "full", "worst")


def norm(word: str) -> str:
    """One spelling for one word, so the paper and the transcript can meet."""
    word = word.strip(".,;:()[]\"'").lower()
    word = re.sub(r"our$", "or", word)
    word = re.sub(r"tre$", "ter", word)
    word = re.sub(r"ise$", "ize", word)
    return word


def said_set(text: str) -> set[str]:
    """Every form of every transcript word, including the halves of a hyphen."""
    out: set[str] = set()
    for token in re.split(r"\s+", text or ""):
        one = norm(token)
        if not one:
            continue
        out.add(one)
        out.add(one.replace("-", ""))
        for piece in one.split("-"):
            if piece:
                out.add(piece)
    return out


def safe(word: str) -> str:
    """Paper tokens carry degree and minus signs; cp949 cannot print them."""
    return word.encode("ascii", "replace").decode()


def auc(good: list[dict], bad: list[dict], way: str) -> float:
    """Chance that a said word outscores an unsaid one. 0.5 is a coin flip."""
    ranked = sorted(x[way] for x in good)
    total = 0.0
    for one in bad:
        value = one[way]
        lo = bisect.bisect_left(ranked, value)
        hi = bisect.bisect_right(ranked, value)
        total += (len(ranked) - hi) + 0.5 * (hi - lo)
    return total / (len(ranked) * len(bad))


def line90(values: list[float], keep: float = 0.90) -> float:
    ranked = sorted(values)
    at = int(round((1.0 - keep) * (len(ranked) - 1)))
    return ranked[max(0, min(at, len(ranked) - 1))]


def score_table(rows: list[dict], title: str) -> dict:
    good = [r for r in rows if not r["bad"]]
    bad = [r for r in rows if r["bad"]]
    print(f"\n{title}: {len(good)} said, {len(bad)} not said")
    print("  score     auc     line   catches")
    out = {}
    for way in WAYS:
        line = line90([x[way] for x in good])
        caught = sum(1 for x in bad if x[way] < line)
        print(f"  {way:<8} {auc(good, bad, way):.3f}  {line:>6.3f}"
              f"   {caught}/{len(bad)} {caught / len(bad):.0%}")
        out[way] = {
            "auc": auc(good, bad, way), "line": line,
            "caught": caught, "targets": len(bad),
        }
    return out


def main() -> int:
    rows = json.loads(SCORED.read_text(encoding="utf-8"))
    cards = {}
    for path in TAKES.glob("*.json"):
        one = json.loads(path.read_text(encoding="utf-8"))
        cards[one["stem"]] = one

    before = score_table(rows, "label as first written")

    flipped = 0
    for row in rows:
        said = said_set(cards[row["stem"]].get("heard") or "")
        was = row["bad"]
        row["bad"] = 0 if norm(row["word"]) in said else 1
        flipped += was != row["bad"]
    print(f"\n{flipped} labels changed")

    after = score_table(rows, "label rebuilt")

    good = [r for r in rows if not r["bad"]]
    bad = [r for r in rows if r["bad"]]

    print("\nwhat is left in the unsaid pile that still scores high")
    left = collections.Counter(
        safe(x["word"]).lower() for x in bad if x["full"] > 0.85
    )
    print(f"  {sum(1 for x in bad if x['full'] > 0.85)} words above 0.85: "
          + ", ".join(f"{w} {n}" for w, n in left.most_common(12)))

    print("\nhow the two piles spread (full score)")
    for name, pile in (("said", good), ("not said", bad)):
        vals = sorted(x["full"] for x in pile)
        cut = [vals[int(p * (len(vals) - 1))] for p in (0.1, 0.25, 0.5, 0.75, 0.9)]
        print(f"  {name:<9} " + "  ".join(
            f"{p}% {v:.2f}" for p, v in zip((10, 25, 50, 75, 90), cut)))

    print("\nby reading speed, one line for everybody")
    line = line90([x["full"] for x in good])
    by = collections.defaultdict(lambda: {"g": [], "b": []})
    for row in rows:
        by[row["tier"]]["b" if row["bad"] else "g"].append(row)
    print(f"  shared line {line:.3f}")
    print("  tier  said-avg  unsaid-avg    auc    kept   caught")
    tiers = {}
    for tier in sorted(by):
        g, b = by[tier]["g"], by[tier]["b"]
        kept = sum(1 for x in g if x["full"] >= line)
        hit = sum(1 for x in b if x["full"] < line)
        print(f"  {tier:>4}   {stat.mean(x['full'] for x in g):>7.3f}"
              f"   {stat.mean(x['full'] for x in b):>9.3f}"
              f"  {auc(g, b, 'full'):.3f}"
              f"   {kept}/{len(g)}   {hit}/{len(b)} {hit / len(b):.0%}")
        tiers[tier] = {
            "said": stat.mean(x["full"] for x in g),
            "unsaid": stat.mean(x["full"] for x in b),
            "auc": auc(g, b, "full"),
            "kept": kept, "keepable": len(g),
            "caught": hit, "targets": len(b),
        }

    print("\nby reading speed, its own line keeping 90% of that speed")
    print("  tier   own line   catches")
    for tier in sorted(by):
        g, b = by[tier]["g"], by[tier]["b"]
        own = line90([x["full"] for x in g])
        hit = sum(1 for x in b if x["full"] < own)
        print(f"  {tier:>4}   {own:>8.3f}   {hit}/{len(b)} {hit / len(b):.0%}")
        tiers[tier]["own_line"] = own
        tiers[tier]["own_caught"] = hit

    print("\nby how many sounds the reference word has")
    print("  sounds  words   said-avg  unsaid-avg    auc")
    byn = collections.defaultdict(lambda: {"g": [], "b": []})
    for row in rows:
        byn[row["n"]]["b" if row["bad"] else "g"].append(row)
    lens = {}
    for n in sorted(byn):
        g, b = byn[n]["g"], byn[n]["b"]
        if len(g) < 20 or len(b) < 20:
            continue
        print(f"  {n:>6}  {len(g) + len(b):>5}   {stat.mean(x['full'] for x in g):>7.3f}"
              f"   {stat.mean(x['full'] for x in b):>9.3f}  {auc(g, b, 'full'):.3f}")
        lens[n] = {"auc": auc(g, b, "full"), "words": len(g) + len(b)}

    OUT.write_text(json.dumps({
        "before": before, "after": after, "flipped": flipped,
        "tiers": tiers, "lengths": lens,
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\nwrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
