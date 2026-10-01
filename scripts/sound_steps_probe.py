"""design/377 - say each slot's score as a count of wrong sounds.

An overlap of 0.600 is hard to argue with and easy to misread. The same number as
"nine of fifteen sounds matched, six did not" is a thing a person can check. And it
shows what the ratio hides: a word only has as many possible scores as it has
sounds, so the line falls between two of them and one sound decides the word.

    python scripts/sound_steps_probe.py .cache/ev416.jsonl 5
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
    line = (d.get("line_used") or 0) / 1000
    print(f"line {line:.3f}  ({line * 100:.1f} out of 100)")
    print()
    print("word                sounds  wrong  score  verdict   one fewer wrong")
    for w, ref in zip(words, refs):
        n = len(split_phone_units(ref))
        if n < MIN_UNITS:
            print(f"{w[:18]:<18}  {n:5d}      -      -  not asked")
            continue
        got = best_window_overlap(split_phone_units(ref), heard)
        wrong = round((1 - got) * n)
        better = 1 - max(wrong - 1, 0) / n
        verdict = "pass" if got >= line else "FAIL"
        flip = "would pass" if better >= line > got else ""
        print(f"{w[:18]:<18}  {n:5d}  {wrong:5d}  {got:.3f}  {verdict:<8}"
              f"  {better:.3f} {flip}")

    print()
    print("what one sound is worth, by how many sounds the word has:")
    for n in (3, 4, 5, 7, 9, 12, 15):
        print(f"  {n:2d} sounds -> one sound moves the score by {1 / n:.3f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
