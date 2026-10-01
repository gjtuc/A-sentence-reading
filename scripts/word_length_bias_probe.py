"""design/377 - does the compare score word length instead of reading quality?

The replay of a half-read sentence showed every short word at 1.000 and every long
word between 0.33 and 0.60, which is the shape of a measuring error rather than a
reading. A short reference is a short window, and a short window can be found by
accident anywhere in a long take; a long reference has to match almost exactly.

If that is what is happening, overlap falls as reference length rises on takes that
were read properly too, and the pass line then sorts words by how long they are.

    python scripts/word_length_bias_probe.py .cache/ev416.jsonl

Phone strings are never printed.
"""

from __future__ import annotations

import json
import pathlib
import statistics as stat
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "src"))

from sentence_reading.llm.phone_match import (  # noqa: E402
    best_window_overlap,
    split_phone_units,
)

MIN_UNITS = 3


def rows(path: pathlib.Path) -> list[dict]:
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
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

    # (reference length in sounds, overlap, was the take read properly)
    seen: list[tuple[int, float, bool]] = []
    for i, r in enumerate(takes, 1):
        d = r.get("details") or {}
        refs = [w.strip() for w in str(d.get("target_phones") or "").split("|")]
        heard = split_phone_units(str(d.get("heard_phones") or ""))
        if not heard or not any(refs):
            continue
        # Take 5 is the half-read one; the rest were read through.
        clean = i != 5
        for ref in refs:
            units = split_phone_units(ref)
            if len(units) < MIN_UNITS:
                continue
            seen.append((len(units), best_window_overlap(units, heard), clean))

    for label, clean in (("read through", True), ("half read", False)):
        pick = [(n, s) for n, s, c in seen if c is clean]
        if not pick:
            continue
        print()
        print(f"== {label}: {len(pick)} words")
        print("  reference sounds   words   mean overlap   passed at 0.60")
        for lo, hi in ((3, 4), (5, 6), (7, 8), (9, 11), (12, 99)):
            band = [s for n, s in pick if lo <= n <= hi]
            if not band:
                continue
            share = sum(1 for s in band if s >= 0.60) / len(band)
            name = f"{lo}-{hi}" if hi < 99 else f"{lo}+"
            print(f"  {name:<18} {len(band):5d}   {stat.mean(band):.3f}"
                  f"          {share:.0%}")
        lens = [n for n, _ in pick]
        scores = [s for _, s in pick]
        if len(set(lens)) > 1:
            r_val = stat.correlation(lens, scores)
            print(f"  correlation of length with overlap: {r_val:+.3f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
