#!/usr/bin/env python3
"""design/169l L0 — pull evidence and compute cache-level figure verdicts.

Usage:
  python scripts/evidence_verdict.py --cache-id 4ba79db36946 --since 6h
  python scripts/evidence_verdict.py --since 2h --fail-on translate_ok_figure_broken
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from sentence_reading.llm.evidence_verdict import compute_cache_verdicts  # noqa: E402

FIGURE_KINDS = (
    "open_ko_summary,figure_preserve_miss,figure_preserve_skip,figure_meta_write,"
    "figure_meta_regress,figure_data_url_miss,figure_window_empty,figure_window_res,"
    "figure_window_req,artifact_derive,artifact_observe,artifact_transfer,"
    "ingest_integrity_violation,progress_view"
)


def _pull(since: str, cache_id: str) -> list[dict]:
    cmd = [
        sys.executable,
        str(ROOT / "scripts/pull_evidence.py"),
        "--since",
        since,
        "--kind",
        FIGURE_KINDS,
        "--merge-ops",
        "--limit",
        "400",
    ]
    if cache_id:
        cmd.extend(["--cache", cache_id])
    proc = subprocess.run(
        cmd,
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
    )
    if proc.returncode != 0:
        print(proc.stderr or proc.stdout, file=sys.stderr)
        raise SystemExit(proc.returncode)
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


def _discover_cache_ids(rows: list[dict]) -> list[str]:
    counts: dict[str, int] = {}
    for r in rows:
        cid = (r.get("cache_id") or "").strip()
        if cid:
            counts[cid] = counts.get(cid, 0) + 1
    return sorted(counts.keys(), key=lambda c: counts[c], reverse=True)


def main() -> int:
    ap = argparse.ArgumentParser(description="169l cache figure verdicts")
    ap.add_argument("--cache-id", default="", help="cache_id (optional if inferring from pull)")
    ap.add_argument("--since", default="6h")
    ap.add_argument(
        "--fail-on",
        default="",
        help="comma-separated verdict prefixes; exit 1 if any match",
    )
    args = ap.parse_args()

    cache_id = (args.cache_id or "").strip()
    rows = _pull(args.since, cache_id)
    if not rows:
        print("no evidence rows", file=sys.stderr)
        return 0

    cache_ids = [cache_id] if cache_id else _discover_cache_ids(rows)
    if not cache_ids:
        print("no cache_id in evidence", file=sys.stderr)
        return 0

    fail_prefixes = [p.strip() for p in args.fail_on.split(",") if p.strip()]
    any_fail = False

    for cid in cache_ids:
        verdicts, last_ev = compute_cache_verdicts(cid, rows)
        print(f"=== CACHE {cid} ===")
        if verdicts:
            print("figure_verdicts:")
            for v in verdicts:
                print(f"  {v}")
                if fail_prefixes and any(v.startswith(p) for p in fail_prefixes):
                    any_fail = True
        else:
            print("figure_verdicts: (none)")
        if last_ev:
            print("last_figure_events:")
            for line in last_ev:
                print(f"  {line}")
        print()

    return 1 if any_fail else 0


if __name__ == "__main__":
    raise SystemExit(main())
