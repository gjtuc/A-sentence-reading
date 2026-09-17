# -*- coding: utf-8 -*-
"""Collect visible import cards from the phone. No paper body to stdout."""
from __future__ import annotations

import re
import subprocess
import time
import xml.etree.ElementTree as ET
from pathlib import Path

ADB = r"C:\Users\user\AppData\Local\Android\Sdk\platform-tools\adb.exe"
SERIAL = "R3CN20QX4BH"
DUMP = Path(r"D:\.cursor\repos\A-sentence-reading\data\ui_cmp.xml")


def adb(*args: str) -> None:
    subprocess.check_call([ADB, "-s", SERIAL, *args])


def dump() -> ET.Element:
    adb("shell", "uiautomator", "dump", "/sdcard/ui_cmp.xml")
    subprocess.check_call([ADB, "-s", SERIAL, "pull", "/sdcard/ui_cmp.xml", str(DUMP)])
    return ET.parse(DUMP).getroot()


def folder_label(root: ET.Element) -> str:
    for n in root.iter("node"):
        t = (n.attrib.get("text") or n.attrib.get("content-desc") or "").strip()
        if t.startswith("폴더:"):
            return t
    return ""


def cards(root: ET.Element) -> list[dict[str, str]]:
    out = []
    for n in root.iter("node"):
        t = n.attrib.get("content-desc") or n.attrib.get("text") or ""
        if ".pdf" not in t.lower() and ".docx" not in t.lower():
            continue
        lines = [ln.strip() for ln in t.split("\n") if ln.strip()]
        files = []
        role = ""
        title = lines[0] if lines else ""
        for ln in lines:
            if ".pdf" in ln.lower() or ".docx" in ln.lower():
                files.extend(part.strip() for part in ln.split("+"))
            if "추정 SI" in ln:
                role = "si"
            elif "추정 메인" in ln:
                role = "main"
            elif "메인+SI" in ln and not role:
                role = "set"
        if files:
            out.append({"files": " | ".join(files), "role": role or "unknown", "title": title[:80]})
    return out


def main() -> None:
    for _ in range(8):
        adb("shell", "input", "swipe", "540", "900", "540", "1750", "200")
        time.sleep(0.25)
    time.sleep(0.5)
    seen: dict[str, dict[str, str]] = {}
    label = ""
    for i in range(14):
        root = dump()
        label = folder_label(root) or label
        batch = cards(root)
        new = 0
        for c in batch:
            if c["files"] not in seen:
                new += 1
            seen[c["files"]] = c
        print(f"pass {i} cards {len(batch)} new {new} total {len(seen)}", flush=True)
        if i > 0 and new == 0:
            break
        adb("shell", "input", "swipe", "540", "1700", "540", "900", "350")
        time.sleep(0.8)
    out = Path(r"D:\.cursor\repos\A-sentence-reading\data\_phone_cards.txt")
    lines = [label.encode("unicode_escape").decode()]
    for c in seen.values():
        lines.append(
            f"{c['role']}\t{c['files'].encode('unicode_escape').decode()}\t{c['title'].encode('unicode_escape').decode()}"
        )
    out.write_text("\n".join(lines), encoding="utf-8")
    print("wrote", len(seen), flush=True)


if __name__ == "__main__":
    main()
