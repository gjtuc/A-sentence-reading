#!/usr/bin/env python3
"""Phone USB + evidence poll every 30s during upload test."""

from __future__ import annotations

import json
import re
import subprocess
import sys
import time
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ADB = Path(r"C:\Users\user\Downloads\scrcpy-win64-v3.3.1\adb.exe")
OUT = ROOT / ".tmp_phone_track"
POLL_S = 30
KST = timezone(timedelta(hours=9))


def _kst() -> str:
    return datetime.now(KST).strftime("%H:%M:%S")


def _adb(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(ADB), *args],
        capture_output=True,
        text=True,
        check=False,
        encoding="utf-8",
        errors="replace",
    )


def _dump_ui(n: int) -> Path:
    OUT.mkdir(parents=True, exist_ok=True)
    remote = "/sdcard/asr_ui_track.xml"
    local = OUT / f"ui_{n:04d}.xml"
    _adb("shell", "uiautomator", "dump", remote)
    _adb("pull", remote, str(local))
    return local


def _screenshot(n: int) -> Path:
    OUT.mkdir(parents=True, exist_ok=True)
    remote = "/sdcard/asr_phone_track.png"
    local = OUT / f"phone_{n:04d}.png"
    _adb("shell", "screencap", "-p", remote)
    _adb("pull", remote, str(local))
    return local


def _ui_hints(xml_path: Path) -> str:
    if not xml_path.is_file() or xml_path.stat().st_size < 20:
        return "no_ui"
    raw = xml_path.read_text(encoding="utf-8", errors="replace")
    keys = (
        "다듬", "번역", "업로드", "실패", "중단", "완료", "보관",
        "진행", "느립", "처리", "연습", "새로고침", "이어서", "분석",
    )
    hits = [k for k in keys if k in raw]
    pcts = re.findall(r"(\d{1,3})\s*%", raw)
    pct = pcts[-1] if pcts else "-"
    return f"pct~{pct} hits={','.join(hits) or '-'}"


def _pull_evidence() -> str:
    proc = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "pull_evidence.py"),
            "--since",
            "20m",
            "--merge-ops",
            "--limit",
            "50",
        ],
        capture_output=True,
        text=True,
        check=False,
        cwd=str(ROOT),
        encoding="utf-8",
        errors="replace",
    )
    rows = []
    for line in (proc.stdout or "").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    kinds = Counter(r.get("kind") for r in rows)
    jobs = sorted({r.get("job_id") for r in rows if r.get("job_id")})
    interesting = []
    watch = {
        "ingest_upload_start", "ingest_started", "ingest_phase_transition",
        "ingest_terminal", "client_hang", "server_job_terminal_error",
        "worker_lost", "library_list_miss", "papers_upload_fail",
        "shadowing_ensure_done", "client_api_timeout",
    }
    for r in rows:
        k = str(r.get("kind") or "")
        if k in watch or r.get("ok") is False:
            interesting.append(
                f"{str(r.get('ts',''))[11:19]} {k} st={r.get('stage')} p={r.get('percent')} j={r.get('job_id')}"
            )
    top = ",".join(f"{a}:{b}" for a, b in kinds.most_common(6))
    jobs_s = ",".join(jobs[-3:]) if jobs else "-"
    tail = " || ".join(interesting[-4:]) if interesting else "-"
    s = f"jobs={jobs_s} kinds={top} last=[{tail}]"
    return s.encode("ascii", errors="backslashreplace").decode("ascii")


def _safe_print(msg: str) -> None:
    line = msg.encode("utf-8", errors="replace").decode("utf-8", errors="replace")
    try:
        print(line, flush=True)
    except UnicodeEncodeError:
        print(line.encode("ascii", errors="backslashreplace").decode("ascii"), flush=True)


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
    except Exception:
        pass
    _safe_print(f"PHONE_TRACK start poll={POLL_S}s out={OUT}")
    if not ADB.is_file():
        print("ADB missing", flush=True)
        return 2
    n = 0
    while True:
        n += 1
        try:
            ui = _dump_ui(n)
            shot = _screenshot(n)
            hints = _ui_hints(ui)
            ev = _pull_evidence()
            _safe_print(f"[{_kst()}] #{n} ui={hints} shot={shot.name} | {ev}")
        except Exception as exc:  # noqa: BLE001
            _safe_print(f"[{_kst()}] #{n} ERR {exc}")
        time.sleep(POLL_S)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        raise SystemExit(0)
