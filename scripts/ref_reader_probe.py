"""design/377 - which reader wrote the reference each take was scored against?

design/373 can tell eSpeak's dictionary IPA from the waveform model's tokens by the
symbols only eSpeak writes: stress marks and ties, none of which are in the model's
392-token vocabulary. The client now detects those rows and asks for a replacement,
but nothing stops it from scoring against the stale row while the replacement is
still being built. If that is what happened, every word of the sentence is being
compared against a notation it can never match, and the result looks uniformly
mediocre no matter how well the sentence was read.

    python scripts/ref_reader_probe.py .cache/ev416.jsonl

Phone strings are never printed. Only which marker classes appear, and how often.
"""

from __future__ import annotations

import json
import pathlib
import sys

# The marks design/373 looks for. Named, so the report never prints the symbol.
MARKS = {
    "primary_stress": "\u02c8",
    "secondary_stress": "\u02cc",
    "zero_width_joiner": "\u200d",
    "tie_above": "\u0361",
    "tie_below": "\u035c",
    "length_mark": "\u02d0",
}
ESPEAK_ONLY = ("primary_stress", "secondary_stress", "zero_width_joiner",
               "tie_above", "tie_below")


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


def census(text: str) -> dict[str, int]:
    return {name: text.count(ch) for name, ch in MARKS.items() if text.count(ch)}


def main() -> int:
    src = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else ".cache/ev416.jsonl")
    takes = [
        r
        for r in rows(src)
        if r.get("kind") == "practice_skill_align"
        and (r.get("details") or {}).get("phase") == "align"
    ]
    takes.sort(key=lambda r: str(r.get("ts") or ""))

    for i, r in enumerate(takes, 1):
        d = r.get("details") or {}
        target = str(d.get("target_phones") or "")
        heard = str(d.get("heard_phones") or "")
        t_marks = census(target)
        h_marks = census(heard)
        stale = any(k in t_marks for k in ESPEAK_ONLY)
        print()
        print(f"-- take {i}  slots {d.get('slot_n')}"
              f"  passed {d.get('sound_pass_n')}  line {d.get('line_used')}")
        print(f"   reference marks: {t_marks or 'none'}")
        print(f"   take marks:      {h_marks or 'none'}")
        print(f"   reference written by eSpeak: {stale}")
        # Space-separated groups on each side. The model writes one token per group;
        # eSpeak writes a whole word per group.
        tg = target.split()
        print(f"   reference groups {len(tg)}, longest {max((len(g) for g in tg), default=0)}"
              f" chars")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
