#!/usr/bin/env python3
"""Monitor Cloud Run cold state via Logging only (no HTTP — does not wake service)."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone

SERVICE = "asr-sentence-reading"
REGION = "asia-northeast3"
IDLE_MINUTES = 15  # Cloud Run scale-to-zero idle window (approx)
POLL_SECONDS = 30


def _gcloud_bin() -> str:
    found = shutil.which("gcloud")
    if found:
        return found
    candidates = [
        r"C:\Program Files (x86)\Google\Cloud SDK\google-cloud-sdk\bin\gcloud.cmd",
        r"C:\Program Files\Google\Cloud SDK\google-cloud-sdk\bin\gcloud.cmd",
    ]
    for c in candidates:
        if c and __import__("pathlib").Path(c).is_file():
            return c
    raise FileNotFoundError("gcloud")


def _last_request_utc() -> datetime | None:
    filt = (
        'resource.type="cloud_run_revision" '
        f'AND resource.labels.service_name="{SERVICE}" '
        'AND httpRequest.requestUrl!=""'
    )
    proc = subprocess.run(
        [
            _gcloud_bin(),
            "logging",
            "read",
            filt,
            "--limit=1",
            "--format=json",
            "--freshness=2h",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "").strip()
        print(f"LOG_ERR {err}", flush=True)
        return None
    raw = (proc.stdout or "").strip()
    if not raw or raw == "[]":
        return None
    try:
        rows = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not rows:
        return None
    ts = (rows[0].get("timestamp") or "").strip()
    if not ts:
        return None
    if ts.endswith("Z"):
        ts = ts[:-1] + "+00:00"
    return datetime.fromisoformat(ts).astimezone(timezone.utc)


def main() -> int:
    print(
        f"COLD_MONITOR start service={SERVICE} idle_target={IDLE_MINUTES}m poll={POLL_SECONDS}s",
        flush=True,
    )
    ready_announced = False
    while True:
        now = datetime.now(timezone.utc)
        last = _last_request_utc()
        if last is None:
            idle_min = None
            status = "no_recent_logs"
        else:
            idle_min = (now - last).total_seconds() / 60.0
            status = "warm" if idle_min < IDLE_MINUTES else "cold_likely"

        kst_now = now + timedelta(hours=9)
        stamp = kst_now.strftime("%H:%M:%S")

        if last is None:
            line = f"[{stamp}] last_request=unknown status={status}"
        else:
            last_kst = (last + timedelta(hours=9)).strftime("%H:%M:%S")
            line = (
                f"[{stamp}] last_request={last_kst}KST "
                f"idle={idle_min:.1f}m need>={IDLE_MINUTES}m status={status}"
            )
        print(line, flush=True)

        if status == "cold_likely" and not ready_announced:
            print(
                "READY_FOR_UPLOAD - server likely asleep; upload now (you wake it).",
                flush=True,
            )
            ready_announced = True
        elif status == "warm":
            ready_announced = False

        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        raise SystemExit(0)
