#!/usr/bin/env python3
"""design/169p — thin CLI: shadowing verdicts from JSONL stdin or --jsonl."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from sentence_reading.llm.shadowing_verdict import (  # noqa: E402
    ShadowingTimeline,
    compute_shadowing_verdicts,
)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--jsonl", default="")
    ap.add_argument("--cache-id", default="")
    ap.add_argument("--budget-s", type=float, default=90.0)
    args = ap.parse_args()
    raw = ""
    if args.jsonl:
        raw = Path(args.jsonl).read_text(encoding="utf-8")
    else:
        raw = sys.stdin.read()
    events = []
    for line in raw.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    tl = ShadowingTimeline.from_events(events, cache_id=args.cache_id.strip())
    vs = compute_shadowing_verdicts(tl, budget_s=args.budget_s)
    print(json.dumps({"cache_id": tl.cache_id, "verdicts": vs, "n": len(tl.events)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
