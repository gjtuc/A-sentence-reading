#!/usr/bin/env python3
"""design/173 — capacity baseline snapshot (before tuning 173a/b/c).

Captures live Run shape + evidence counts so phase changes are comparable.
No secrets printed. Auth-only routes are not probed (use phone repro + evidence).

Examples:
  python scripts/capacity_baseline_snapshot.py --since 24h
  python scripts/capacity_baseline_snapshot.py --since 7d --out data/capacity_baseline_pre_173a.json
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from pull_evidence import (  # noqa: E402
    _filter_rows,
    _gsutil_cat,
    _load_lines,
    _parse_since,
)
from verify_live_status import DEFAULT_URL, fetch_status  # noqa: E402

SERVICE = "asr-sentence-reading"
REGION = "asia-northeast3"

# design/173 — primary signals for gate/capacity work
BASELINE_KINDS = frozenset(
    {
        "client_api_timeout",
        "client_api_fail",
        "stall_fired",
        "client_hang",
        "ingest_upload_start",
        "server_job_terminal_error",
        "translate_call_slow",
        "translate_phase_exit",
        "open_ko_summary",
    }
)

ACCESS_ROUTES = frozenset(
    {
        "access_status",
        "auth_status",
        "auth_bootstrap",
    }
)


def _git_head() -> str:
    try:
        r = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        return (r.stdout or "").strip() if r.returncode == 0 else ""
    except OSError:
        return ""


def _cloud_run_spec() -> dict:
    """Best-effort gcloud describe; empty dict if CLI missing."""
    try:
        r = subprocess.run(
            [
                "gcloud",
                "run",
                "services",
                "describe",
                SERVICE,
                f"--region={REGION}",
                "--format=json",
            ],
            capture_output=True,
            text=True,
            check=False,
            timeout=90,
        )
    except (OSError, subprocess.TimeoutExpired):
        return {}
    if r.returncode != 0:
        return {"error": (r.stderr or r.stdout or "gcloud_failed")[:300]}
    try:
        data = json.loads(r.stdout or "{}")
    except json.JSONDecodeError:
        return {"error": "gcloud_json_parse_failed"}
    spec = data.get("spec", {}).get("template", {}).get("spec", {})
    meta = data.get("spec", {}).get("template", {}).get("metadata", {}).get(
        "annotations", {}
    )
    container = (spec.get("containers") or [{}])[0]
    limits = (container.get("resources") or {}).get("limits") or {}
    return {
        "revision": data.get("status", {}).get("latestReadyRevisionName", ""),
        "cpu": limits.get("cpu"),
        "memory": limits.get("memory"),
        "container_concurrency": spec.get("containerConcurrency"),
        "timeout_seconds": spec.get("timeoutSeconds"),
        "min_scale": meta.get("autoscaling.knative.dev/minScale"),
        "max_scale": meta.get("autoscaling.knative.dev/maxScale"),
        "cpu_throttling": meta.get("run.googleapis.com/cpu-throttling"),
        "startup_cpu_boost": meta.get("run.googleapis.com/startup-cpu-boost"),
    }


def _load_evidence_rows(*, since, bucket_prefix: str) -> list[dict]:
    prefix = bucket_prefix.rstrip("/")
    uri = f"{prefix}/evidence/events.jsonl"
    try:
        raw = _gsutil_cat(uri)
    except RuntimeError as exc:
        return [{"_error": str(exc)[:400]}]
    rows = _load_lines(raw)
    return _filter_rows(rows, since=since, kinds=set(), job="", cache="")


def _summarize_evidence(rows: list[dict]) -> dict:
    if rows and rows[0].get("_error"):
        return {"error": rows[0]["_error"], "rows": 0}

    kind_counts: Counter[str] = Counter()
    access_timeouts: Counter[str] = Counter()
    access_timeout_total = 0
    for row in rows:
        kind = str(row.get("kind") or "")
        kind_counts[kind] += 1
        if kind != "client_api_timeout":
            continue
        details = row.get("details")
        route = ""
        if isinstance(details, dict):
            route = str(details.get("route") or "")
        elif isinstance(details, str):
            m = re.search(r"route[=:]\s*([a-z_]+)", details, re.I)
            route = m.group(1) if m else ""
        if route in ACCESS_ROUTES or "access" in route or "auth" in route:
            access_timeouts[route or "(unknown)"] += 1
            access_timeout_total += 1

    baseline = {k: kind_counts.get(k, 0) for k in sorted(BASELINE_KINDS)}
    return {
        "rows_in_window": len(rows),
        "kind_counts_baseline": baseline,
        "client_api_timeout_by_route": dict(access_timeouts),
        "access_auth_timeout_total": access_timeout_total,
        "top_kinds": dict(kind_counts.most_common(12)),
    }


def build_snapshot(
    *,
    status_url: str,
    since_raw: str,
    bucket_prefix: str,
) -> dict:
    since = _parse_since(since_raw)
    if since_raw and since is None:
        raise ValueError(f"invalid_since:{since_raw}")

    status: dict = {}
    status_err = ""
    try:
        status = fetch_status(status_url)
    except Exception as exc:  # noqa: BLE001
        status_err = f"{type(exc).__name__}:{exc}"

    evidence_rows = _load_evidence_rows(since=since, bucket_prefix=bucket_prefix)

    return {
        "schema": "asr_capacity_baseline_v1",
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "window_since": since_raw,
        "git_head": _git_head(),
        "live_status": {
            "ok": status.get("ok"),
            "version": status.get("version"),
            "deploy_git_sha": status.get("deploy_git_sha"),
            "pipeline_version": status.get("pipeline_version"),
            "access_gate_enabled": status.get("access_gate_enabled"),
            "access_gate_ttl_s": status.get("access_gate_ttl_s"),
            "error": status_err or None,
        },
        "cloud_run": _cloud_run_spec(),
        "evidence": _summarize_evidence(evidence_rows),
        "notes": [
            "173a not shipped until access_gate_ttl_s appears on /api/status",
            "access/status latency p95 requires server timing or Cloud Logging — not in this snapshot",
            "Repro under load: open+translate paper, then poll Settings or resume app",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="ASR capacity baseline snapshot (design/173)")
    p.add_argument("--url", default=DEFAULT_URL, help="Live /api/status URL")
    p.add_argument(
        "--since",
        default="24h",
        help="Evidence window (24h, 7d, or ISO)",
    )
    p.add_argument(
        "--bucket-prefix",
        default="gs://asr-chaheon-warehouse/asr",
        help="GCS evidence prefix",
    )
    p.add_argument(
        "--out",
        default="",
        help="Write JSON snapshot to file (default stdout only)",
    )
    args = p.parse_args(argv)

    try:
        snap = build_snapshot(
            status_url=args.url,
            since_raw=args.since,
            bucket_prefix=args.bucket_prefix,
        )
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    text = json.dumps(snap, ensure_ascii=False, indent=2)
    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(text + "\n", encoding="utf-8")
        print(f"wrote {out_path}", file=sys.stderr)
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
