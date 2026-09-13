#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""design/256 — pull or load evidence and print ingest-queue readiness verdicts.

Examples:
  python scripts/track_ingest_queue.py --events .tmp_ev_investigate.jsonl
  python scripts/track_ingest_queue.py --since 24h
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from sentence_reading.llm.ingest_queue_verdict import (  # noqa: E402
    compute_ingest_queue_verdicts,
)


def _load_events(path: Path) -> list[dict]:
    rows: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            o = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(o, dict):
            rows.append(o)
    return rows


def _pull(since: str, out: Path) -> list[dict]:
    cmd = [
        sys.executable,
        str(ROOT / "scripts" / "pull_evidence.py"),
        "--since",
        since,
        "--out",
        str(out),
    ]
    subprocess.run(cmd, check=False)
    if not out.is_file():
        return []
    return _load_events(out)


def main() -> int:
    ap = argparse.ArgumentParser(description="Track ingest-queue causal verdicts")
    ap.add_argument("--events", type=Path, help="JSONL evidence file")
    ap.add_argument("--since", default="24h", help="pull_evidence window when no --events")
    ap.add_argument(
        "--out",
        type=Path,
        default=ROOT / ".tmp_ev_ingest_queue.jsonl",
        help="pull output path",
    )
    args = ap.parse_args()

    if args.events:
        events = _load_events(args.events)
    else:
        events = _pull(args.since, args.out)

    verdicts = compute_ingest_queue_verdicts(events)
    print(json.dumps({"event_n": len(events), "verdicts": verdicts}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
