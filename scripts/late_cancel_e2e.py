#!/usr/bin/env python3
"""Device E2E: 132 late cancel (cancel_too_late UI)."""
from __future__ import annotations

import re
import subprocess
import sys
import time

ADB = r"C:\Users\user\AppData\Local\Android\Sdk\platform-tools\adb.exe"

LATE_KW = ("읽기 시작", "읽기 준비", "번역 준비", "번역 중", "저장 중", "연습 구간")
EARLY_KW = ("다듬", "비전", "그림", "품질", "추출", "페이지 이미지", "조각")


def run(*args: str, check: bool = False) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [ADB, *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=check,
    )


def dump(path: str = "/sdcard/u.xml") -> str:
    run("shell", "uiautomator", "dump", path)
    return run("exec-out", "cat", path).stdout


def focus_line() -> str:
    for line in run("shell", "dumpsys", "window").stdout.splitlines():
        if "mCurrentFocus" in line:
            return line.strip()
    return ""


def tap(x: int, y: int) -> None:
    run("shell", "input", "tap", str(x), str(y))


def dismiss_overlays() -> None:
    fl = focus_line()
    if "NotificationShade" in fl:
        run("shell", "input", "keyevent", "KEYCODE_BACK")
        time.sleep(0.6)
    if "GrantPermissions" in focus_line():
        tap(540, 1984)
        time.sleep(0.8)


def library_count(xml: str) -> int | None:
    m = re.search(r"보관 (\d+)건", xml)
    return int(m.group(1)) if m else None


def progress_line(xml: str) -> str:
    m = re.search(r'(?:text|content-desc)="(처리 중[^"]*)"', xml)
    if m:
        return m.group(1)
    m = re.search(r"처리 중[^\"<]{0,160}", xml)
    return m.group(0) if m else ""


def cancel_button(xml: str) -> tuple[int, int] | None:
    m = re.search(
        r'(?:content-desc|text)="취소"[^>]*bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"',
        xml,
    )
    if not m:
        return None
    x1, y1, x2, y2 = map(int, m.groups())
    return (x1 + x2) // 2, (y1 + y2) // 2


def stage_segment(prog: str) -> str:
    """Middle segment of '처리 중 N% · <stage> · …' (ignore boilerplate suffix)."""
    parts = [p.strip() for p in prog.split("·")]
    if len(parts) >= 2:
        return parts[1]
    return prog


def is_late_stage(prog: str) -> bool:
    stage = stage_segment(prog)
    if any(k in stage for k in LATE_KW):
        return True
    pct_m = re.search(r"(\d+)%", prog)
    pct = int(pct_m.group(1)) if pct_m else -1
    # Server ready floor is 88%; stage text can lag one poll behind percent.
    return pct >= 88


def pick_pdf(rows: list[tuple[str, int, int]], prefer: str = "") -> tuple[str, int, int]:
    """Prefer multi-page PDFs that stay in ingest long enough to hit ready (88%)."""
    if prefer:
        for r in rows:
            if prefer in r[0]:
                return r
    skip = ("AnalysisReport", "3슬라이드", "5슬라이드")
    order = ("CVD정의", "DRM 반응", "7슬라이드", "그림1")
    for key in order:
        for r in rows:
            if key in r[0] and not any(s in r[0] for s in skip):
                return r
    for r in rows:
        if not any(s in r[0] for s in skip):
            return r
    return rows[0]


def pct_from_prog(prog: str) -> int:
    m = re.search(r"(\d+)%", prog)
    return int(m.group(1)) if m else -1


def main() -> int:
    prefer = ""
    if len(sys.argv) > 1:
        prefer = sys.argv[1]
    sys.stdout.reconfigure(encoding="utf-8")

    run("shell", "am", "start", "-n", "com.gjtuc.sentence_reading/.MainActivity")
    time.sleep(2.0)
    # Close leftover DocumentsUI from a prior abort.
    for _ in range(3):
        fl = focus_line().lower()
        if "documentsui" in fl or "pickactivity" in fl:
            run("shell", "input", "keyevent", "KEYCODE_BACK")
            time.sleep(0.8)
        else:
            break
    tap(180, 2132)
    time.sleep(2.0)

    baseline = None
    for _ in range(8):
        xml = dump()
        baseline = library_count(xml)
        if baseline is not None:
            break
        time.sleep(1.2)
    if baseline is None:
        print("ABORT: library header missing", flush=True)
        return 1
    print(f"baseline={baseline}", flush=True)

    # If an ingest is already mid-flight, attach and wait for late cancel.
    xml0 = dump()
    if progress_line(xml0) and cancel_button(xml0):
        print("ATTACH existing upload:", progress_line(xml0), flush=True)
    else:
        # Open DocumentsUI via PDF import button (bounds from dump when possible).
        picker_ok = False
        for attempt in range(6):
            xml = dump()
            m = re.search(
                r'(?:text|content-desc)="PDF 가져오기"[^>]*bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"',
                xml,
            )
            if m:
                a, b, c, d = map(int, m.groups())
                tap((a + c) // 2, (b + d) // 2)
            else:
                tap(849, 199)
            time.sleep(2.5)
            dismiss_overlays()
            fl = focus_line().lower()
            if "documentsui" in fl or "pickactivity" in fl:
                picker_ok = True
                break
            print(f"picker_retry {attempt}: {focus_line()}", flush=True)
            time.sleep(0.8)
        if not picker_ok:
            print("ABORT: picker not open:", focus_line(), flush=True)
            return 1

        xml = dump("/sdcard/p.xml")
        rows: list[tuple[str, int, int]] = []
        for m in re.finditer(
            r'text="([^"]+\.pdf)"[^>]*bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"',
            xml,
            re.I,
        ):
            name = m.group(1)
            x1, y1, x2, y2 = map(int, m.groups()[1:])
            if x2 > 0 and y2 > 0 and y1 > 100:
                rows.append((name, (x1 + x2) // 2, (y1 + y2) // 2))
        if not rows:
            print("ABORT: no pdf in picker", flush=True)
            return 1
        pick = pick_pdf(rows, prefer)
        print(f"pick={pick[0][:50]} @{pick[1]},{pick[2]}", flush=True)
        tap(pick[1], pick[2])
        time.sleep(2)
        dismiss_overlays()

    cancelled = False
    saw = False
    last = ""
    idle = 0
    for i in range(2400):
        dismiss_overlays()
        fl = focus_line()
        if "sentence_reading" not in fl and "documentsui" not in fl.lower():
            print("LEFT", fl, flush=True)
            run("shell", "input", "keyevent", "KEYCODE_BACK")
            time.sleep(0.3)
            continue

        xml = dump()
        later = re.search(
            r'(?:text|content-desc)="나중에"[^>]*bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"',
            xml,
        )
        if later:
            a, b, c, d = map(int, later.groups())
            tap((a + c) // 2, (b + d) // 2)
            time.sleep(0.3)

        prog = progress_line(xml)
        if prog:
            saw = True
            idle = 0
            if prog != last:
                print(f"{i}:{prog}", flush=True)
                last = prog
        else:
            idle += 1

        btn = cancel_button(xml)
        if btn and saw and prog and is_late_stage(prog):
            print(f"LATE_CANCEL @{btn[0]},{btn[1]} :: {prog}", flush=True)
            tap(*btn)
            cancelled = True
            break

        if i > 120 and saw and not btn and "처리 중" not in xml:
            idle += 1
            if idle >= 24:
                print("ENDED before late window", flush=True)
                break
        if i > 120 and not saw:
            print("NO_PROGRESS", flush=True)
            break

        pct = pct_from_prog(prog) if prog else -1
        if pct >= 78:
            continue  # tight loop — no sleep while approaching ready
        time.sleep(0.2)
    else:
        print("TIMEOUT", flush=True)

    hit_msg = False
    for j in range(90):
        time.sleep(2)
        dismiss_overlays()
        xml = dump()
        if "거의 끝나" in xml:
            m = re.search(r'(?:text|content-desc)="([^"]*거의 끝나[^"]*)"', xml)
            print("HIT_MSG", m.group(1) if m else "yes", flush=True)
            hit_msg = True
            # do not break — wait for processing to finish after too-late refuse
        if saw and "처리 중" not in xml and j >= 3:
            if hit_msg or cancelled:
                print("processing_done", j, flush=True)
                break
            if not cancelled:
                print("processing_done", j, flush=True)
                break

    tap(180, 2132)
    time.sleep(1.5)
    # Library list can lag publish — pull 새로고침 once.
    xml = dump()
    m = re.search(
        r'(?:text|content-desc)="새로고침"[^>]*bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"',
        xml,
    )
    if m:
        a, b, c, d = map(int, m.groups())
        tap((a + c) // 2, (b + d) // 2)
        time.sleep(2.5)
    xml = dump()
    final = library_count(xml)
    delta = (final - baseline) if final is not None else "?"
    print(
        f"RESULT baseline={baseline} final={final} delta={delta} "
        f"cancelled={cancelled} hit_msg={hit_msg}",
        flush=True,
    )
    for pat in ("거의 끝나", "그대로 완료", "업로드를 취소", "처리에 실패"):
        if pat in xml:
            print("HIT", pat, flush=True)

    return 0 if cancelled and hit_msg and final == baseline + 1 else 2


if __name__ == "__main__":
    raise SystemExit(main())
