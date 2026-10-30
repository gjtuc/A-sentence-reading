# -*- coding: utf-8 -*-
"""design/495 — build SentenceReadingHelper.exe and upload it for the settings download.

Runs inside click 02 after the deploy. Skips when the helper sources are the
same as the last upload (click/out/helper_uploaded.txt). The server streams the
object at GET /api/helper/download (mobile_apk_gcs.py).

    python scripts/build_helper_exe.py [--force] [--no-upload]
"""
from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCES = ("helper_app.py", "helper_store.py", "usb_sync_bridge.py")
STAMP = ROOT / "click" / "out" / "helper_uploaded.txt"
DIST = ROOT / ".cache" / "helper_dist"
WORK = ROOT / ".cache" / "helper_build"
EXE = DIST / "SentenceReadingHelper.exe"
BUCKET = os.environ.get("ASR_GCS_BUCKET", "asr-chaheon-warehouse")
PREFIX = os.environ.get("ASR_GCS_PREFIX", "asr")
OBJECT = f"{PREFIX}/mobile/sentence-reading-helper.exe"


def sources_hash() -> str:
    h = hashlib.sha256()
    for name in SOURCES:
        h.update(name.encode())
        h.update((ROOT / "scripts" / name).read_bytes())
    return h.hexdigest()[:16]


def ensure_pyinstaller() -> bool:
    try:
        import PyInstaller  # noqa: F401

        return True
    except ImportError:
        pass
    print("installing pyinstaller")
    rc = subprocess.run([sys.executable, "-m", "pip", "install", "--user", "pyinstaller"]).returncode
    return rc == 0


def build() -> bool:
    if not ensure_pyinstaller():
        print("pyinstaller install failed")
        return False
    shutil.rmtree(WORK, ignore_errors=True)
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm", "--onefile", "--noconsole",
        "--name", EXE.stem,
        "--paths", str(ROOT / "scripts"),
        "--collect-submodules", "websockets",
        "--distpath", str(DIST),
        "--workpath", str(WORK),
        "--specpath", str(WORK),
        str(ROOT / "scripts" / "helper_app.py"),
    ]
    rc = subprocess.run(cmd, cwd=ROOT).returncode
    ok = rc == 0 and EXE.is_file()
    print(f"build: {'ok' if ok else f'failed (exit {rc})'} {EXE if ok else ''}".rstrip())
    return ok


def upload() -> bool:
    gsutil = shutil.which("gsutil") or shutil.which("gsutil.cmd")
    if not gsutil:
        print("gsutil not found (Google Cloud SDK)")
        return False
    rc = subprocess.run([gsutil, "cp", str(EXE), f"gs://{BUCKET}/{OBJECT}"]).returncode
    print(f"upload: {'ok' if rc == 0 else f'failed (exit {rc})'} gs://{BUCKET}/{OBJECT}")
    return rc == 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--no-upload", action="store_true")
    args = ap.parse_args()
    want = sources_hash()
    try:
        have = STAMP.read_text(encoding="utf-8").strip()
    except OSError:
        have = ""
    if have == want and not args.force:
        print(f"helper up to date ({want})")
        return 0
    if not build():
        return 1
    if args.no_upload:
        return 0
    if not upload():
        return 1
    STAMP.parent.mkdir(parents=True, exist_ok=True)
    STAMP.write_text(want, encoding="utf-8")
    print(f"helper uploaded ({want})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
