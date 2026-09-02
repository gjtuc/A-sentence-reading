#!/usr/bin/env python3
"""design/169k K0 — linked translate track: phone UI + evidence + verdict rules.

Usage:
  python scripts/track_translate.py
  python scripts/track_translate.py --no-ui
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from sentence_reading.llm.track_verdict import JobTimeline, compute_verdicts  # noqa: E402
from sentence_reading.llm.evidence_verdict import compute_cache_verdicts  # noqa: E402

ADB = Path(r"C:/Users/user/Downloads/scrcpy-win64-v3.3.1/adb.exe")
STATE = ROOT / ".tmp_track_state.json"
UI_XML = ROOT / ".tmp_ui_track.xml"
PHONE_PNG = ROOT / ".tmp_phone_track.png"
OUT = ROOT / ".tmp_track_latest.txt"

KINDS = (
    "translate_phase_enter,translate_phase_exit,translate_call_start,"
    "translate_call_done,translate_call_slow,translate_call_fail,"
    "translate_item_done,translate_save_ko,open_ko_summary,"
    "stall_fired,server_job_terminal_error,figure_preserve_miss,"
    "progress_view,handoff,checkpoint,artifact_transfer,artifact_observe,"
    "artifact_derive,artifact_invalidate"
)


def _run(cmd: list[str], timeout: int = 60) -> subprocess.CompletedProcess[str]:
    env = dict(__import__("os").environ)
    env["MSYS2_ARG_CONV_EXCL"] = "*"
    env["PYTHONIOENCODING"] = "utf-8"
    return subprocess.run(
        cmd,
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        env=env,
    )


def _bash(script: str, timeout: int = 60) -> subprocess.CompletedProcess[str]:
    return _run(["bash", "-lc", script], timeout=timeout)


def capture_ui() -> dict:
    if not ADB.is_file():
        return {"ok": False, "error": "adb_missing"}
    adb = str(ADB).replace("\\", "/")
    png = str(PHONE_PNG).replace("\\", "/")
    _bash(
        f'MSYS2_ARG_CONV_EXCL="*" "{adb}" exec-out screencap -p > "{png}"',
        timeout=40,
    )
    _run([str(ADB), "shell", "uiautomator", "dump", "/sdcard/window_dump.xml"], timeout=30)
    cat = _run([str(ADB), "exec-out", "cat", "/sdcard/window_dump.xml"], timeout=30)
    UI_XML.write_text(cat.stdout or "", encoding="utf-8")
    if not (cat.stdout or "").strip():
        return {"ok": False, "error": "empty_ui"}
    root = ET.fromstring(cat.stdout)
    lines: list[str] = []
    pct = None
    status = ""
    for n in root.iter("node"):
        d = (n.attrib.get("content-desc") or n.attrib.get("text") or "").strip()
        if not d:
            continue
        if any(
            k in d
            for k in (
                "%",
                "번역",
                "처리",
                "보관",
                "취소",
                "실패",
                "완료",
                "0.3",
                "재분석",
                "준비",
                "섹션",
            )
        ):
            one = d.replace("\n", " | ")[:200]
            if one not in lines:
                lines.append(one)
        m = re.search(r"(\d+)\s*%", d)
        if m and ("처리" in d or "번역" in d or "분석" in d):
            pct = int(m.group(1))
            status = d.replace("\n", " | ")[:200]
    return {"ok": True, "pct": pct, "status": status, "lines": lines}


def pull_evidence(since: str = "90m") -> list[dict]:
    p = _run(
        [
            sys.executable,
            str(ROOT / "scripts/pull_evidence.py"),
            "--since",
            since,
            "--kind",
            KINDS,
            "--merge-ops",
            "--limit",
            "400",
        ],
        timeout=90,
    )
    rows: list[dict] = []
    for line in (p.stdout or "").splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def fmt_ev(o: dict) -> str:
    d = o.get("details") or {}
    bits = [o.get("kind") or "?"]
    if d.get("section"):
        bits.append(f"sec={d['section']}")
    if d.get("call_kind"):
        bits.append(str(d["call_kind"]))
    if d.get("batch_n") is not None:
        bits.append(f"n={d['batch_n']}")
    if "chunk_i" in d:
        bits.append(f"ch={d['chunk_i']}/{d.get('chunk_n')}")
    if d.get("elapsed_ms") is not None:
        bits.append(f"{d['elapsed_ms']}ms")
    if d.get("ko_sentence_n") is not None:
        bits.append(f"ko_s={d['ko_sentence_n']}")
    if d.get("index") is not None:
        bits.append(f"i={d['index']}")
    return " ".join(str(b) for b in bits)


def analyze(ui: dict, rows: list[dict], prev: dict) -> dict:
    by_job: dict[str, list[dict]] = defaultdict(list)
    for o in rows:
        jid = o.get("job_id") or ""
        if str(jid).startswith("job_"):
            by_job[jid].append(o)

    active_job = None
    active_ts = ""
    for j, evs in by_job.items():
        for o in evs:
            ts = o.get("ts") or ""
            if ts >= active_ts:
                active_ts = ts
                active_job = j

    open_starts: dict[tuple, dict] = {}
    hangs: list[str] = []
    sections_done: list[str] = []
    last_calls: list[str] = []
    track_kinds = {
        "stall_fired",
        "server_job_terminal_error",
        "figure_preserve_miss",
        "open_ko_summary",
        "checkpoint",
        "handoff",
        "progress_view",
        "artifact_transfer",
        "artifact_observe",
    }

    if active_job:
        by_job[active_job].sort(key=lambda o: o.get("ts") or "")
        for o in by_job[active_job]:
            k = o.get("kind") or ""
            d = o.get("details") or {}
            if (
                k
                and not str(k).startswith("translate")
                and k not in track_kinds
            ):
                continue
            key = (d.get("call_kind"), d.get("section"), d.get("chunk_i"))
            if k == "translate_call_start":
                open_starts[key] = o
            elif k in ("translate_call_done", "translate_call_fail"):
                open_starts.pop(key, None)
                if (
                    k == "translate_call_done"
                    and d.get("call_kind") == "google_batch"
                    and d.get("section")
                ):
                    sections_done.append(str(d["section"]))
            ts_short = (o.get("ts") or "")[11:19]
            if k == "checkpoint" and d.get("checkpoint"):
                rem = d.get("remaining")
                extra = f" rem={rem}" if rem is not None else ""
                last_calls.append(
                    f"{ts_short} checkpoint={d.get('checkpoint')} "
                    f"blocked={d.get('blocked_on') or '-'}{extra} "
                    f"sec={d.get('section') or '-'}"
                )
            elif k == "server_job_terminal_error":
                last_calls.append(
                    f"{ts_short} TERMINAL {d.get('reason_enum') or d.get('reason') or 'error'}"
                )
            elif k == "figure_preserve_miss":
                miss = d.get("missing_locators") or []
                last_calls.append(
                    f"{ts_short} figure_preserve_miss prior={d.get('prior_png')} "
                    f"miss_n={len(miss)}"
                )
            elif k and str(k).startswith("translate"):
                last_calls.append(f"{ts_short} {fmt_ev(o)}")
            elif k == "progress_view" and o.get("percent") is not None:
                last_calls.append(f"{ts_short} progress_view pct={o.get('percent')}")
            elif k == "handoff":
                last_calls.append(
                    f"{ts_short} handoff {d.get('from_stage')}→{d.get('to_stage')}"
                )

    for _key, o in open_starts.items():
        hangs.append(f"OPEN {fmt_ev(o)} since={(o.get('ts') or '')[11:19]}")

    cache_ids = sorted(
        {o.get("cache_id") for o in (by_job.get(active_job) or []) if o.get("cache_id")}
    )

    pct = ui.get("pct")
    job_events = by_job.get(active_job) or []
    last = job_events[-1] if job_events else None
    last_kind = (last or {}).get("kind")
    last_ts = (last or {}).get("ts") or ""
    silence_s = None
    if last_ts:
        try:
            last_dt = datetime.fromisoformat(last_ts.replace("Z", "+00:00"))
            silence_s = int((datetime.now(timezone.utc) - last_dt).total_seconds())
        except Exception:
            silence_s = None

    tl = JobTimeline.from_events(job_events) if active_job else JobTimeline()
    if active_job:
        verdict = compute_verdicts(
            tl,
            ui_pct=pct,
            open_hangs=hangs,
            silence_s=silence_s,
            prev=prev,
        )
    else:
        verdict = ["no_recent_translate_evidence"]

    if pct is not None and prev.get("ui_pct") == pct:
        stuck_n = int(prev.get("pct_stuck_n") or 0) + 1
    else:
        stuck_n = 0

    from sentence_reading.llm.track_verdict import check_169j_section_pass

    figure_verdict: list[str] = []
    figure_last: list[str] = []
    primary_cache = cache_ids[0] if cache_ids else ""
    if primary_cache:
        figure_verdict, figure_last = compute_cache_verdicts(primary_cache, rows)

    return {
        "ts_local": datetime.now().strftime("%H:%M:%S"),
        "ui_pct": pct,
        "ui_status": ui.get("status") or "",
        "ui_lines": ui.get("lines") or [],
        "active_job": active_job,
        "cache_ids": cache_ids,
        "sections_done": sections_done,
        "hangs": hangs,
        "last_calls": last_calls[-14:],
        "verdict": verdict,
        "pct_stuck_n": stuck_n,
        "silence_s": silence_s,
        "last_kind": last_kind,
        "job_event_n": {j: len(evs) for j, evs in by_job.items()},
        "accept_169j_title": check_169j_section_pass(tl, "title") if active_job else None,
        "figure_verdict": figure_verdict,
        "figure_last_events": figure_last,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Linked translate track (169k)")
    ap.add_argument("--no-ui", action="store_true", help="Skip adb UI capture")
    ap.add_argument("--since", default="90m")
    args = ap.parse_args()

    prev: dict = {}
    if STATE.is_file():
        try:
            prev = json.loads(STATE.read_text(encoding="utf-8"))
        except Exception:
            prev = {}

    ui = (
        {"ok": True, "pct": None, "status": "", "lines": []}
        if args.no_ui
        else capture_ui()
    )
    rows = pull_evidence(args.since)
    snap = analyze(
        ui if ui.get("ok") else {"pct": None, "status": "", "lines": []},
        rows,
        prev,
    )
    snap["ui_ok"] = bool(ui.get("ok"))
    if not ui.get("ok"):
        snap["ui_error"] = ui.get("error")

    STATE.write_text(json.dumps(snap, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        f"=== LINKED TRACK {snap['ts_local']} ===",
        f"UI: {snap['ui_pct']}% | {snap['ui_status'] or '(no status)'}",
        f"JOB: {snap['active_job']}  cache={','.join(snap['cache_ids']) or '-'}",
        f"sections_done(batch): {','.join(snap['sections_done']) or '-'}",
        f"silence_s: {snap.get('silence_s')}  last_kind: {snap.get('last_kind')}",
        f"169j_title: {snap.get('accept_169j_title')}",
        f"hangs: {'; '.join(snap['hangs']) or 'none'}",
        f"verdict: {'; '.join(snap['verdict'])}",
        f"figure_verdict: {'; '.join(snap.get('figure_verdict') or []) or 'none'}",
        "last_calls:",
    ]
    lines.extend(f"  {x}" for x in snap["last_calls"])
    fig_last = snap.get("figure_last_events") or []
    if fig_last:
        lines.append("last_figure_events:")
        lines.extend(f"  {x}" for x in fig_last)
    text = "\n".join(lines) + "\n"
    OUT.write_text(text, encoding="utf-8")
    print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
