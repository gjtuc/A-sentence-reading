"""design/377 - replay one take's compare, slot by slot, from the evidence alone.

`slot_hits` says which printed words failed but not why. `phone_pairs` carries what
the scorer actually held up against each other, so the compare can be re-run here
and the failures sorted into causes: the reference was missing, the word's sounds
were nowhere in the take, or they were there and the line refused them.

    python scripts/slot_pair_probe.py .cache/ev416.jsonl 5

Phone strings are never printed. Only counts, overlaps, and where in the take the
best match sat.
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
    d = (takes[want - 1].get("details") or {})

    for key in ("slot_pieces", "phone_pairs"):
        raw = str(d.get(key) or "")
        print(f"== {key}: {len(raw)} chars")
        if not raw:
            continue
        # Shape only: how it is punctuated tells how it is grouped.
        marks = {c: raw.count(c) for c in "|/,;: " if raw.count(c)}
        print(f"   separators {marks}")
        head = raw[:120]
        print(f"   ascii skeleton {''.join(c if c.isascii() else '.' for c in head)}")

    hits = str(d.get("slot_hits") or "")
    target = str(d.get("target_phones") or "")
    heard = str(d.get("heard_phones") or "")
    tgt_units = split_phone_units(target)
    heard_units = split_phone_units(heard)
    print()
    print(f"slot_hits {hits}")
    print(f"reference {len(tgt_units)} sounds, heard {len(heard_units)} sounds")

    # The scorer asks each printed word's sounds against the whole take. Without
    # the per-word split in the row, the next best thing is to ask how much of the
    # reference is findable in the take at all, in order, in chunks the size of a
    # word. If the front of the reference is findable and the front of the sheet
    # failed anyway, the fault is in which heard sounds the slot was given.
    print()
    print("reference walked in 7-sound chunks, best match anywhere in the take:")
    step = 7
    for i in range(0, len(tgt_units), step):
        chunk = tgt_units[i:i + step]
        if len(chunk) < 3:
            continue
        got = best_window_overlap(chunk, heard_units)
        where = i / max(len(tgt_units), 1)
        print(f"   sounds {i:3d}-{i + len(chunk) - 1:3d}"
              f"  ({where:4.0%} in)  overlap {got:.3f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
