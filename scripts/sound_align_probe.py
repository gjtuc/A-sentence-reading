"""design/377 - re-run one take's compare exactly as the scorer did it.

`target_phones` is already cut per printed word by ` | `, so the scorer's own
question can be asked again here: each word's reference sounds against the whole
run of heard sounds, best window, against the line that take was judged by. The
run is checked against `slot_hits` first -- if it does not reproduce the sheet, the
numbers below are not the ones the reader saw and nothing should be concluded.

    python scripts/sound_align_probe.py .cache/ev416.jsonl 5

Phone strings are never printed. Only counts and overlaps.
"""

from __future__ import annotations

import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "src"))

from sentence_reading.llm.phone_match import (  # noqa: E402
    best_window_overlap,
    split_phone_units,
)

# skill_score.dart: a reference this short matches almost anything, so the word
# cannot be asked about and leaves the sheet with a dash.
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
    want = int(sys.argv[2]) if len(sys.argv) > 2 else 5
    takes = [
        r
        for r in rows(src)
        if r.get("kind") == "practice_skill_align"
        and (r.get("details") or {}).get("phase") == "align"
    ]
    takes.sort(key=lambda r: str(r.get("ts") or ""))
    d = takes[want - 1].get("details") or {}

    words = [w.strip() for w in str(d.get("slot_pieces") or "").split("|")]
    refs = [w.strip() for w in str(d.get("target_phones") or "").split("|")]
    heard = split_phone_units(str(d.get("heard_phones") or ""))
    hits = str(d.get("slot_hits") or "")
    line = (d.get("line_used") or 0) / 1000

    print(f"take {want}: {len(words)} printed words, {len(refs)} reference groups,"
          f" {len(heard)} heard sounds, line {line:.3f}")
    if len(words) != len(refs):
        print("  word count and reference count disagree; not comparable")
        return 1

    got = []
    rebuilt = []
    for ref in refs:
        units = split_phone_units(ref)
        if len(units) < MIN_UNITS:
            got.append(None)
            rebuilt.append("-")
            continue
        score = best_window_overlap(units, heard)
        got.append(score)
        rebuilt.append("1" if score >= line else "0")
    rebuilt_s = "".join(rebuilt)

    agree = sum(1 for a, b in zip(rebuilt_s, hits) if a == b)
    print(f"sheet    {hits}")
    print(f"rebuilt  {rebuilt_s}")
    print(f"agrees on {agree} of {len(hits)} slots")
    if agree < len(hits):
        print("  NOTE: not an exact replay. The Dart unit split keeps the length")
        print("  mark that the python one strips, so a word holding one differs.")

    print()
    print("word by word, with how far each sat from the line:")
    for i, (w, s) in enumerate(zip(words, got), 1):
        if s is None:
            print(f"  {i:2d} {w[:18]:<18} unaskable (reference under 3 sounds)")
            continue
        gap = s - line
        side = "pass" if gap >= 0 else "FAIL"
        bar = "#" * round(s * 20)
        print(f"  {i:2d} {w[:18]:<18} {s:.3f} {side} {gap:+.3f}  {bar}")

    asked = [s for s in got if s is not None]
    near = [s for s in asked if 0 <= line - s <= 0.1]
    print()
    print(f"asked {len(asked)}, passed {sum(1 for s in asked if s >= line)}")
    print(f"failed within 0.10 of the line: {len(near)}")
    half = len(asked) // 2
    print(f"front half mean overlap {sum(asked[:half]) / max(half, 1):.3f}")
    print(f"back  half mean overlap {sum(asked[half:]) / max(len(asked) - half, 1):.3f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
