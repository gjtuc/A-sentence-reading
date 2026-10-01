"""design/377 - what state was each sentence's reference in when it was scored?

One sentence came back unscored. design/374 made the client ask again only while the
server says the reference is coming, so the question is whether it asked, what it was
told, and whether the answer arrived before the reader spoke.

    python scripts/ref_state_probe.py .cache/ev416.jsonl
"""

from __future__ import annotations

import json
import pathlib
import sys


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


KEYS = (
    "chunk_index", "code", "sound_ref_code", "sound_ref_status", "phone_span_n",
    "stale_span_n", "ask_n", "ref_code", "span_n", "source", "sound_ref_fail",
)


def main() -> int:
    src = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else ".cache/ev416.jsonl")
    all_rows = rows(src)
    kinds = {}
    for r in all_rows:
        kinds[r.get("kind")] = kinds.get(r.get("kind"), 0) + 1
    print("rows by kind:")
    for k, v in sorted(kinds.items(), key=lambda kv: -kv[1]):
        print(f"   {v:4d}  {k}")

    for kind in ("practice_skill_spoken", "practice_skill_align"):
        print()
        print(f"== {kind}")
        for r in all_rows:
            if r.get("kind") != kind:
                continue
            d = r.get("details") or {}
            if kind == "practice_skill_align" and d.get("phase") == "align":
                continue
            shown = {k: d[k] for k in KEYS if k in d}
            print(f"   {r.get('ts')}  {shown}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
