"""Build the taskbar button that opens the 문장읽기 web app.

    python scripts/web_launcher/build.py

Writes %LOCALAPPDATA%\\Programs\\SentenceReadingWeb\\SentenceReadingWeb.exe with the phone
app's icon, and a 「문장읽기 웹」 shortcut on the desktop. The exe lives outside the repo
so a checkout or clean never breaks the pinned button.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from PIL import Image

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
ICON_PNG = ROOT / "mobile" / "android" / "app" / "src" / "main" / "res" / "mipmap-xxxhdpi" / "ic_launcher.png"
CSC = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Microsoft.NET" / "Framework64" / "v4.0.30319" / "csc.exe"
OUT_DIR = Path(os.environ["LOCALAPPDATA"]) / "Programs" / "SentenceReadingWeb"
EXE = OUT_DIR / "SentenceReadingWeb.exe"
ICO = OUT_DIR / "sentence_reading_web.ico"


def make_icon() -> None:
    img = Image.open(ICON_PNG).convert("RGBA")
    img.save(ICO, sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (192, 192)])


def compile_exe() -> None:
    subprocess.run(
        [
            str(CSC),
            "/nologo",
            "/codepage:65001",
            "/target:winexe",
            f"/win32icon:{ICO}",
            f"/out:{EXE}",
            str(HERE / "sentence_reading_web.cs"),
        ],
        check=True,
    )


def desktop_shortcut() -> Path:
    desktop = Path(os.environ["USERPROFILE"]) / "Desktop"
    lnk = desktop / "문장읽기 웹.lnk"
    script = (
        "$s = (New-Object -ComObject WScript.Shell).CreateShortcut($env:ASR_LNK);"
        "$s.TargetPath = $env:ASR_EXE;"
        "$s.WorkingDirectory = $env:ASR_DIR;"
        "$s.IconLocation = $env:ASR_EXE + ',0';"
        "$s.Description = '문장읽기 웹';"
        "$s.Save()"
    )
    env = dict(os.environ, ASR_LNK=str(lnk), ASR_EXE=str(EXE), ASR_DIR=str(OUT_DIR))
    subprocess.run(["powershell", "-NoProfile", "-Command", script], check=True, env=env)
    return lnk


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    make_icon()
    compile_exe()
    lnk = desktop_shortcut()
    print(f"exe {EXE}")
    print(f"shortcut {lnk}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
