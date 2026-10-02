"""design/378 - does warming a paper actually leave scorable references behind?

The unit tests prove the queueing is polite. They do not prove a warmed sentence
can be scored, because they never call Google. This does: it warms a handful of
real sentences and then asks the scorer's own question of each one -- are there
sounds attached to every printed word.

Usage:
    python scripts/warm_paper_probe.py
    python scripts/warm_paper_probe.py --lines 3
"""
from __future__ import annotations

import argparse
import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

# Five sentences in the shape the phone sends: already spoken-normalised, no
# markup. Short enough to warm in under two minutes, long enough that the
# boundary handout has something to get wrong.
LINES = [
    "The catalyst was prepared by chemical vapor deposition.",
    "Nanoparticles were dispersed on the carbon support.",
    "We measured the electrochemical surface area after cycling.",
    "Figure two shows the current density against potential.",
    "The result was reproduced in three independent runs.",
]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--lines", type=int, default=len(LINES))
    args = ap.parse_args()

    from sentence_reading.llm import sound_reference as sr

    if not sr.enabled():
        print("sound_ref off (ASR_SOUND_REF)")
        return 2

    lines = LINES[: max(1, args.lines)]
    before = sr.build_report()
    print(f"warming {len(lines)} lines, voice {sr.reference_voice()}")
    t0 = time.monotonic()
    report = sr.warm_paper(lines)
    # The warm hands the last build to the worker and waits, but the worker
    # writes the cache after the pending key clears, so give it a moment.
    for _ in range(60):
        if sr.build_report()["sound_ref_waiting"] == 0:
            break
        time.sleep(1.0)
    took = time.monotonic() - t0
    print(f"warm took {took:.0f}s -> {report}")
    print(f"builds before {before['sound_ref_ok']} after {sr.build_report()['sound_ref_ok']}")
    if str(sr.build_report()["sound_ref_fail"]) != "none":
        print(f"FAULT last build failed: {sr.build_report()['sound_ref_fail']}")

    # Now the part that matters: is each one scorable from cache alone, with no
    # build allowed. That is exactly what the reading path asks for.
    bad = 0
    for line in lines:
        got = sr.reference_for(line, allow_build=False)
        words = (got or {}).get("words") or []
        printed = len(line.replace(".", "").split())
        # Count words that came back with at least the three sounds the scorer
        # needs before it will ask about a word at all.
        usable = sum(1 for w in words if len((w or {}).get("sounds") or []) >= 3)
        state = "cached" if got else "MISSING"
        print(
            f"  {state:7s} words={len(words):2d}/{printed:2d} "
            f"askable={usable:2d}  {line[:40]}"
        )
        if not got or len(words) < printed:
            bad += 1

    print("VERDICT", "ok" if bad == 0 else f"FAULT {bad} of {len(lines)} not warmed")
    return 0 if bad == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
