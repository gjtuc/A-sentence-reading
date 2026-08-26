#!/usr/bin/env python3
"""Device E2E for design/137 — upload lump137 PDF, expect 2 figures. Phone + Live."""
from __future__ import annotations

import re
import subprocess
import sys
import time

ADB = r"C:\Users\user\AppData\Local\Android\Sdk\platform-tools\adb.exe"
# Long stem so Cloud library save passes _MIN_TITLE_KEY_LEN even if debone misses title section.
DEVICE_PDF = "/sdcard/Download/synthetic_lumped_alpha_beta_nickel_catalysts_drm.pdf"
LIBRARY_NEEDLE = "Lumped Fig Captions"


def dump() -> str:
    subprocess.run(
        [ADB, "shell", "uiautomator", "dump", "/sdcard/u.xml"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    raw = subprocess.check_output([ADB, "exec-out", "cat", "/sdcard/u.xml"])
    return raw.decode("utf-8", errors="replace")


def tap(x: int, y: int) -> None:
    subprocess.run([ADB, "shell", "input", "tap", str(x), str(y)])


def lib_count(u: str) -> int:
    # Prefer Korean header; fall back to counting pdf rows if XML encoding is odd.
    m = re.search(r"보관\s*(\d+)\s*건", u)
    if m:
        return int(m.group(1))
    m = re.search(r'text="보관\s*(\d+)\s*건"', u)
    if m:
        return int(m.group(1))
    # ASCII-safe: count list rows with "pdf" metadata (library entries).
    rows = len(re.findall(r"pdf · 문장", u))
    return rows if rows > 0 else -1


def library_has(u: str, needle: str) -> bool:
    return needle.lower() in u.lower()


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    subprocess.run(
        [ADB, "shell", "am", "start", "-W", "-n", "com.gjtuc.sentence_reading/.MainActivity"],
        stdout=subprocess.DEVNULL,
    )
    time.sleep(2)
    tap(180, 2132)
    time.sleep(1.2)
    u = dump()
    baseline = lib_count(u)
    has_before = library_has(u, LIBRARY_NEEDLE)
    print(f"baseline={baseline} has_entry_before={has_before}", flush=True)
    if baseline < 0 and not has_before:
        print("LOGIN_OR_UI_BLOCK", flush=True)
        return 3

    tap(849, 199)
    time.sleep(2.5)
    p = dump()
    picked = False
    for m in re.finditer(
        r'text="([^"]+)"[^>]*bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"', p
    ):
        label = m.group(1)
        if "synthetic_lumped" in label.lower() or "nickel catalysts" in label.lower():
            x1, y1, x2, y2 = map(int, m.groups()[1:])
            tap((x1 + x2) // 2, (y1 + y2) // 2)
            picked = True
            print(f"picked {label[:60]}", flush=True)
            break
    if not picked:
        print("PICKER_MISS", flush=True)
        return 4

    time.sleep(1)
    last = ""
    for i in range(500):
        time.sleep(0.55)
        u = dump()
        if any(x in u for x in ("구분하지 못했습니다", "덩어리", "여러 그림")):
            print("FAIL_CLOSED_MSG", flush=True)
            return 6
        if "처리 중" in u:
            pm = re.search(r"처리 중[^\"<]{0,100}", u)
            if pm and pm.group(0) != last:
                print(f"{i} {pm.group(0)[:90]}", flush=True)
                last = pm.group(0)
        else:
            cur = lib_count(u)
            if library_has(u, LIBRARY_NEEDLE) and not has_before:
                print("DONE library entry appeared", flush=True)
                break
            if "보관함 저장에 실패" in u or "너무 짧거나 문장이 없어" in u:
                print("SAVE_FAIL_MSG", flush=True)
                return 7
            if cur > baseline >= 0:
                print(f"DONE {baseline}->{cur}", flush=True)
                break
    else:
        print("TIMEOUT", flush=True)
        return 5

    u = dump()
    for m in re.finditer(
        r'text="([^"]+)"[^>]*bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"', u
    ):
        t = m.group(1)
        if LIBRARY_NEEDLE in t and int(m.group(3)) > 280:
            x1, y1, x2, y2 = map(int, m.groups()[1:])
            tap((x1 + x2) // 2, (y1 + y2) // 2)
            print(f"OPEN {t.split('&#10;')[0][:80]}", flush=True)
            break

    time.sleep(4)
    u = dump()
    blob = " | ".join(
        m.group(1) for m in re.finditer(r'(?:text|content-desc)="([^"]+)"', u)
    )
    fi = re.search(r"figure (\d+) / (\d+)", blob, re.I)
    print(f"FIG {fi.group(0) if fi else 'none'}", flush=True)
    if not fi or int(fi.group(2)) < 2:
        print("FIG_COUNT_FAIL", flush=True)
        return 8

    nm = re.search(
        r'content-desc="next figure"[^>]*bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"', u
    )
    if not nm:
        print("NO_NEXT", flush=True)
        return 9
    a, b, c, d = map(int, nm.groups())
    tap((a + c) // 2, (b + d) // 2)
    time.sleep(1.2)
    u2 = dump()
    b2 = " | ".join(
        m.group(1) for m in re.finditer(r'(?:text|content-desc)="([^"]+)"', u2)
    )
    print(
        "AFTER_NEXT",
        re.search(r"figure (\d+) / (\d+)", b2, re.I),
        "Beta" in b2,
        flush=True,
    )
    if "Beta" not in b2:
        return 10
    print("E2E_OK", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
