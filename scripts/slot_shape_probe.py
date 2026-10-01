"""design/377 - where in the sentence did the scorer put its failures?

A reader read the front of a sentence properly and said something unrelated for
the back. That should fail the back and pass the front. If the failures come out
spread evenly instead, the compare is not finding the right place in the take, and
the shape of `slot_hits` says so without anyone reading IPA.

    python scripts/slot_shape_probe.py .cache/ev416.jsonl

Phone strings are never printed: they hold IPA and this console is cp949. Only
their shape -- how many sounds, how many groups, how the groups line up with the
printed words -- comes out.
"""

from __future__ import annotations

import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "src"))

from sentence_reading.llm.phone_match import split_phone_units  # noqa: E402


def rows(path: pathlib.Path) -> list[dict]:
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def halves(hits: str) -> str:
    """Pass rate in the front half against the back half of the sentence."""
    asked = [c for c in hits if c in "01"]
    half = len(asked) // 2
    front, back = asked[:half], asked[half:]
    fp = sum(1 for c in front if c == "1")
    bp = sum(1 for c in back if c == "1")
    return f"front {fp}/{len(front)}   back {bp}/{len(back)}"


def shape(label: str, text: str) -> None:
    """Say how big a phone string is without saying what is in it."""
    if not text:
        print(f"   {label}: empty")
        return
    groups = text.split()
    units = split_phone_units(text)
    print(f"   {label}: {len(groups)} groups, {len(units)} sounds"
          f", group sizes {[len(split_phone_units(g)) for g in groups][:30]}")


def main() -> int:
    src = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else ".cache/ev416.jsonl")
    takes = [
        r
        for r in rows(src)
        if r.get("kind") == "practice_skill_align"
        and (r.get("details") or {}).get("phase") == "align"
    ]
    takes.sort(key=lambda r: str(r.get("ts") or ""))
    print(f"{len(takes)} takes in {src}")

    for i, r in enumerate(takes, 1):
        d = r.get("details") or {}
        hits = str(d.get("slot_hits") or "")
        print()
        print(f"-- take {i}  {r.get('ts')}  slots {d.get('slot_n')}"
              f"  line {d.get('line_used')}  n={d.get('line_n')}")
        print(f"   slot_hits  {hits}      {halves(hits)}")
        shape("target", str(d.get("target_phones") or ""))
        shape("heard  ", str(d.get("heard_phones") or ""))
        spoken = str(d.get("spoken_line") or "")
        print(f"   printed words: {len(spoken.split())}")
        heard_txt = str(d.get("stt_heard") or "")
        print(f"   heard words:   {len(heard_txt.split())}")
        rest = {
            k: v
            for k, v in d.items()
            if k not in {
                "slot_hits", "target_phones", "heard_phones", "spoken_line",
                "stt_heard", "slot_pieces", "phone_pairs", "phase",
            }
        }
        print(f"   {rest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
