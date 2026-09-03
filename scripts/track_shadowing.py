#!/usr/bin/env python3
"""design/169p — pull shadowing evidence + print verdicts.

Usage:
  python scripts/track_shadowing.py --cache-id <id>
  python scripts/track_shadowing.py --since 2h
  python scripts/track_shadowing.py --jsonl path/to/events.jsonl --cache-id <id>
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from sentence_reading.llm.shadowing_verdict import (  # noqa: E402
    ShadowingTimeline,
    compute_shadowing_verdicts,
)

OUT = ROOT / ".tmp_track_shadowing.txt"

KINDS = (
    "shadowing_gate,shadowing_ensure_start,shadowing_ensure_done,"
    "shadowing_boot_start,shadowing_boot_done,shadowing_build_round,"
    "shadowing_loop_event,shadowing_chunks_get,shadowing_chunks_build_start,"
    "shadowing_chunks_build_done,shadowing_gemini_call_start,"
    "shadowing_gemini_call_done,shadowing_ingest_stage,"
    "client_api_fail,client_api_timeout,pref_shadowing_set"
)


def _run(cmd: list[str], timeout: int = 120) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )


def pull_events(*, since: str, cache_id: str) -> list[dict]:
    cmd = [
        sys.executable,
        str(ROOT / "scripts" / "pull_evidence.py"),
        "--since",
        since,
        "--kind",
        KINDS,
    ]
    if cache_id:
        cmd.extend(["--cache", cache_id])
    proc = _run(cmd, timeout=180)
    rows: list[dict] = []
    for line in (proc.stdout or "").splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def load_jsonl(path: Path) -> list[dict]:
    rows: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def main() -> int:
    ap = argparse.ArgumentParser(description="Track shadowing prep evidence")
    ap.add_argument("--cache-id", default="", help="Filter cache_id")
    ap.add_argument("--since", default="6h", help="pull_evidence window")
    ap.add_argument("--jsonl", default="", help="Local JSONL instead of pull")
    ap.add_argument("--budget-s", type=float, default=90.0)
    args = ap.parse_args()

    if args.jsonl:
        events = load_jsonl(Path(args.jsonl))
    else:
        events = pull_events(since=args.since, cache_id=args.cache_id.strip())

    tl = ShadowingTimeline.from_events(events, cache_id=args.cache_id.strip())
    verdicts = compute_shadowing_verdicts(tl, budget_s=args.budget_s)

    lines: list[str] = []
    lines.append(f"# track_shadowing {datetime.now(timezone.utc).isoformat()}")
    lines.append(f"cache_id={tl.cache_id or '(any)'}")
    lines.append(f"events={len(tl.events)}")
    lines.append(f"verdicts={','.join(verdicts) if verdicts else '(none)'}")
    lines.append("--- timeline ---")
    for e in tl.events[-80:]:
        kind = e.get("kind")
        ts = e.get("ts") or ""
        d = e.get("details") if isinstance(e.get("details"), dict) else {}
        ok = e.get("ok")
        code = e.get("code") or ""
        lines.append(
            f"{ts} {kind} ok={ok} code={code} "
            f"plan_status={d.get('plan_status','')} "
            f"gate={d.get('gate','')} chunk_n={d.get('chunk_n','')} "
            f"round={d.get('round','')} phase={d.get('phase','')}"
        )
    text = "\n".join(lines) + "\n"
    OUT.write_text(text, encoding="utf-8")
    print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
