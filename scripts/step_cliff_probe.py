"""design/379 - where exactly is the cliff in the pass line?

A word with n sounds can only ever score 1 - k/n. So the scores a word can take are
steps, and how wide a step is depends on how long the word is: a third of the score
for a three-sound word, a fifteenth for `electrochemical`.

That matters because the line is a single number. If the line happens to sit just
above a step that many words land on, those words fail by a rounding error rather
than by how they were read. This measures that: every score the words in this log
could have taken, and how close the line sits to each.

Usage:
    python scripts/step_cliff_probe.py .cache/ev416.jsonl
"""
from __future__ import annotations

import collections
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from sentence_reading.llm.phone_match import (  # noqa: E402
    best_window_overlap,
    split_phone_units,
)

MIN_UNITS = 3


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


def main() -> int:
    src = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else ".cache/ev416.jsonl")
    takes = [
        r
        for r in rows(src)
        if r.get("kind") == "practice_skill_align"
        and (r.get("details") or {}).get("phase") == "align"
    ]
    takes.sort(key=lambda r: str(r.get("ts") or ""))

    slots: list[tuple[str, int, float, float]] = []  # word, sounds, score, line
    for r in takes:
        d = r.get("details") or {}
        words = [w.strip() for w in str(d.get("slot_pieces") or "").split("|")]
        refs = [w.strip() for w in str(d.get("target_phones") or "").split("|")]
        heard = split_phone_units(str(d.get("heard_phones") or ""))
        line = (d.get("line_used") or 0) / 1000
        if not heard or line <= 0:
            continue
        for w, ref in zip(words, refs):
            units = split_phone_units(ref)
            if len(units) < MIN_UNITS:
                continue
            slots.append((w, len(units), best_window_overlap(units, heard), line))

    if not slots:
        print("no scorable slots in this log")
        return 1

    line = slots[-1][3]
    print(f"{len(slots)} words asked about across {len(takes)} takes, line {line:.3f}")
    print()

    # 1. How wide is one sound, for the words that actually appear?
    lens = collections.Counter(n for _w, n, _s, _l in slots)
    print("one wrong sound costs:")
    for n in sorted(lens):
        print(f"   {n:2d} sounds  {1 / n:.3f}   ({lens[n]} words)")
    print()

    # 2. For each word length, which step does the line fall between, and how far
    #    above the lower step does it sit? A line barely above a step is a cliff.
    print("length  last passing score  first failing score  line sits above it by")
    for n in sorted(lens):
        steps = [1 - k / n for k in range(n + 1)]
        passing = min((s for s in steps if s >= line), default=None)
        failing = max((s for s in steps if s < line), default=None)
        if passing is None or failing is None:
            continue
        gap = line - failing
        flag = "   <-- cliff" if gap <= 0.01 else ""
        print(f"  {n:2d}      {passing:.3f}              {failing:.3f}"
              f"              {gap:+.3f}{flag}")
    print()

    # 3. What actually happened: failures sorted by how far short they fell.
    failed = [(line - s, w, n, s) for w, n, s, _l in slots if s < line]
    failed.sort()
    passed = len(slots) - len(failed)
    print(f"passed {passed}/{len(slots)}, failed {len(failed)}")
    by_sounds = collections.Counter()
    for short, _w, n, _s in failed:
        by_sounds[min(int(short * n + 0.999), 9) or 1] += 1
    print("failures by how many sounds they were short:")
    for k in sorted(by_sounds):
        print(f"   {k} sound{'s' if k > 1 else ' '} short  {by_sounds[k]:3d}")
    print()
    hair = [f for f in failed if f[0] <= 0.01]
    print(f"failed by 0.01 or less (a rounding error, not a reading): {len(hair)}")
    for short, w, n, s in hair[:12]:
        print(f"   {w[:18]:<18} {n:2d} sounds  scored {s:.3f}, short by {short:.3f}")
    print()
    print("reading: a cliff is a line sitting a hair above a score many words land")
    print("on. Moving the line a little *down* lets those words through without")
    print("letting through anything that was read worse.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
