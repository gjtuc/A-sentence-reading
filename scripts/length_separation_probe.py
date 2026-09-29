"""A long word's score says almost nothing. Read off the two-voices rows.

One pass line is used for every word, whatever its length. The rows from
`two_voices_probe.py` say that cannot be right, and not by a little.

A three sound reference scores 1.00 when the reader is correct and 0.50 when they
said a different word. An eight sound reference scores 0.90 correct and 0.88
wrong. The first is a decision; the second is noise. Edit distance divided by the
longer side is the reason: one wrong sound out of three moves the score a third,
one out of eight moves it an eighth, and ordinary variation between two voices
moves it about that much anyway.

So a single line has to be set high enough for long words, which then fails short
words that were fine, or low enough for short words, which passes every long word
however it was said.

This reads the saved rows and reports nothing it did not measure. Setting a line
per length needs far more than the 24 wrong readings here, which is what the 619
human takes are for.
"""
from __future__ import annotations

import json
import pathlib
import statistics as stat
import sys

BUILDS = ("natural|25", "break100|25")


def main() -> int:
    path = pathlib.Path(".cache/two_voices_report.json")
    if not path.exists():
        print("run two_voices_probe.py first")
        return 1
    saved = json.loads(path.read_text(encoding="utf-8"))

    out = {}
    for build in BUILDS:
        rows = [r for r in saved["rowsets"][build] if r["judged"]]
        print(f"== {build}")
        print(f"{'sounds':>7}{'correct reads':>24}{'wrong reads':>18}"
              f"{'apart':>8}")
        print(f"{'':>7}{'n':>6}{'mean':>9}{'worst':>9}{'n':>6}{'mean':>12}")
        per = {}
        for length in sorted({r["ref_units"] for r in rows}):
            keep = [r["ratio"] for r in rows
                    if r["ref_units"] == length and not r["is_target"]]
            wrong = [r["ratio"] for r in rows
                     if r["ref_units"] == length and r["is_target"]]
            if len(keep) < 4 or not wrong:
                continue
            apart = stat.mean(keep) - stat.mean(wrong)
            per[length] = {
                "correct_n": len(keep), "correct_mean": round(stat.mean(keep), 3),
                "correct_worst": round(min(keep), 3), "wrong_n": len(wrong),
                "wrong_mean": round(stat.mean(wrong), 3), "apart": round(apart, 3),
            }
            print(f"{length:>7}{len(keep):>6}{stat.mean(keep):>9.2f}"
                  f"{min(keep):>9.2f}{len(wrong):>6}{stat.mean(wrong):>12.2f}"
                  f"{apart:>8.2f}")
        short = [v["apart"] for k, v in per.items() if k <= 4]
        long_ = [v["apart"] for k, v in per.items() if k >= 7]
        if short and long_:
            print(f"  up to 4 sounds: {stat.mean(short):.2f} apart. "
                  f"7 or more: {stat.mean(long_):.2f} apart.")
        out[build] = per
        print()

    pathlib.Path(".cache/length_separation.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print("wrote .cache/length_separation.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
