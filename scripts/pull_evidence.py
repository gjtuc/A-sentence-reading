#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""design/169 — pull agent evidence (+ optional ops) for debugging.

No admin UI. Agents run this after user reports a failure.

Examples:
  python scripts/pull_evidence.py --since 2h --kind client_api_fail,stall_fired
  python scripts/pull_evidence.py --job job_abc123def456 --merge-ops
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _parse_since(raw: str) -> datetime | None:
    s = (raw or "").strip().lower()
    if not s:
        return None
    now = datetime.now(timezone.utc)
    if s.endswith("h") and s[:-1].isdigit():
        return now - timedelta(hours=int(s[:-1]))
    if s.endswith("m") and s[:-1].isdigit():
        return now - timedelta(minutes=int(s[:-1]))
    if s.endswith("d") and s[:-1].isdigit():
        return now - timedelta(days=int(s[:-1]))
    try:
        if s.endswith("z"):
            s = s[:-1] + "+00:00"
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except ValueError:
        return None


def _parse_ts(raw: str) -> datetime | None:
    s = (raw or "").strip()
    if not s:
        return None
    try:
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except ValueError:
        return None


def _gsutil_cat(uri: str) -> bytes:
    try:
        proc = subprocess.run(
            ["gsutil", "-q", "cat", uri],
            check=False,
            capture_output=True,
        )
    except FileNotFoundError as exc:
        raise RuntimeError(
            "gsutil not found. Install Google Cloud SDK or fix PATH."
        ) from exc
    if proc.returncode != 0:
        err = (proc.stderr or b"").decode("utf-8", errors="replace").strip()
        raise RuntimeError(
            f"gsutil cat failed for {uri} (exit {proc.returncode}): {err or 'no stderr'}"
        )
    return proc.stdout or b""


def _load_lines(raw: bytes) -> list[dict]:
    out: list[dict] = []
    for line in raw.decode("utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict) and obj.get("id"):
            out.append(obj)
    return out


def _filter_rows(
    rows: list[dict],
    *,
    since: datetime | None,
    kinds: set[str],
    job: str,
    cache: str,
) -> list[dict]:
    out: list[dict] = []
    for row in rows:
        if since is not None:
            ts = _parse_ts(str(row.get("ts") or ""))
            if ts is None or ts < since:
                continue
        if kinds:
            if str(row.get("kind") or "") not in kinds:
                continue
        if job and str(row.get("job_id") or "") != job:
            continue
        if cache and str(row.get("cache_id") or "") != cache:
            continue
        out.append(row)
    return out


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Pull ASR evidence JSONL for agents")
    p.add_argument(
        "--bucket-prefix",
        default="gs://asr-chaheon-warehouse/asr",
        help="GCS prefix (default warehouse)",
    )
    p.add_argument("--since", default="6h", help="e.g. 2h, 30m, 1d, or ISO time")
    p.add_argument("--kind", default="", help="comma-separated kinds")
    p.add_argument("--job", default="", help="job_… filter")
    p.add_argument("--cache", default="", help="cache_id filter")
    p.add_argument(
        "--merge-ops",
        action="store_true",
        help="also pull ops_events/events.jsonl",
    )
    p.add_argument("--limit", type=int, default=200, help="max rows to print")
    p.add_argument(
        "--out",
        default="",
        help="optional output file (JSONL); default stdout",
    )
    args = p.parse_args(argv)

    since = _parse_since(args.since)
    if args.since and since is None:
        print(f"invalid --since: {args.since}", file=sys.stderr)
        return 2
    kinds = {k.strip() for k in args.kind.split(",") if k.strip()}
    job = (args.job or "").strip()
    cache = (args.cache or "").strip()
    prefix = args.bucket_prefix.rstrip("/")

    sources = [("evidence", f"{prefix}/evidence/events.jsonl")]
    if args.merge_ops:
        sources.append(("ops", f"{prefix}/ops_events/events.jsonl"))

    merged: list[dict] = []
    for label, uri in sources:
        try:
            raw = _gsutil_cat(uri)
        except RuntimeError as exc:
            print(str(exc), file=sys.stderr)
            return 1
        rows = _load_lines(raw)
        for row in rows:
            row = dict(row)
            row["_stream"] = label
            merged.append(row)

    filtered = _filter_rows(
        merged, since=since, kinds=kinds, job=job, cache=cache
    )
    filtered.sort(key=lambda r: str(r.get("ts") or ""))
    if args.limit > 0:
        filtered = filtered[-args.limit :]

    lines = [json.dumps(r, ensure_ascii=False) for r in filtered]
    text = "\n".join(lines) + ("\n" if lines else "")
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
        print(f"wrote {len(filtered)} rows → {args.out}", file=sys.stderr)
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
