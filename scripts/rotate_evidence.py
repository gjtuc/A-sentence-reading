#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""design/169g phase 6 — rotate evidence (+ ops) JSONL to retention window.

Examples:
  python scripts/rotate_evidence.py
  python scripts/rotate_evidence.py --force --days 7
  python scripts/rotate_evidence.py --ops-only
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    sys.path.insert(0, str(ROOT / "src"))
    parser = argparse.ArgumentParser(description="Rotate evidence/ops JSONL retention")
    parser.add_argument("--days", type=int, default=None, help="Keep window days")
    parser.add_argument("--force", action="store_true", help="Ignore 6h throttle")
    parser.add_argument("--evidence-only", action="store_true")
    parser.add_argument("--ops-only", action="store_true")
    args = parser.parse_args()

    out: dict = {}
    if not args.ops_only:
        from sentence_reading.llm import evidence_bus as eb

        out["evidence"] = eb.rotate_events(keep_days=args.days, force=args.force)
    if not args.evidence_only:
        from sentence_reading.llm import ops_events as oev

        out["ops_events"] = oev.rotate_events(keep_days=args.days, force=args.force)
    print(json.dumps(out, ensure_ascii=False))
    ok = all(bool(v.get("ok")) for v in out.values()) if out else False
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
