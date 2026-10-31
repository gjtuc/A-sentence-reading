# -*- coding: utf-8 -*-
"""design/497 — build the Microsoft Store package (MSIX) of 논문 전송 도우미.

The Store signs MSIX packages itself, so this does not sign. Output:
click/out/SentenceReadingHelper.msix, uploaded by hand in Partner Center.

- PyInstaller one-folder build (no unpacking into a temp folder at every start).
- A second copy of the exe named ...Startup.exe, run by the manifest startup task.
- makeappx comes from the Microsoft.Windows.SDK.BuildTools NuGet package,
  unpacked into .cache/tools (nothing is installed on the PC).
- Identity values come from scripts/helper_msix_identity.json (Partner Center >
  Product identity).

    python scripts/build_helper_msix.py [--layout-only]
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import urllib.request
import zipfile
from pathlib import Path
from xml.sax.saxutils import escape

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from build_helper_exe import ensure_pyinstaller  # noqa: E402

NAME = "SentenceReadingHelper"
IDENTITY = ROOT / "scripts" / "helper_msix_identity.json"
WORK = ROOT / ".cache" / "helper_msix"
LAYOUT = WORK / "layout"
OUT = ROOT / "click" / "out" / f"{NAME}.msix"
TOOLS = ROOT / ".cache" / "tools" / "sdk-buildtools"
NUGET_URL = "https://www.nuget.org/api/v2/package/Microsoft.Windows.SDK.BuildTools"
DISPLAY = "논문 전송 도우미"
DESCRIPTION = "휴대폰과 컴퓨터 사이에서 논문을 USB 선으로 옮기고, 웹에서 받은 논문을 이 컴퓨터에 한 벌 더 보관해요."
ASSETS = {
    "Square44x44Logo.png": 44,
    "Square150x150Logo.png": 150,
    "StoreLogo.png": 50,
    "Square44x44Logo.targetsize-256_altform-unplated.png": 256,
}


def app_version() -> str:
    text = (ROOT / "mobile" / "pubspec.yaml").read_text(encoding="utf-8")
    m = re.search(r"^version:\s*(\d+)\.(\d+)\.(\d+)", text, re.M)
    if not m:
        raise SystemExit("no version in pubspec.yaml")
    return f"{m.group(1)}.{m.group(2)}.{m.group(3)}"


def package_version(app: str) -> str:
    """0.3.510 -> 1.3.510.0 (the Store wants the last part 0 and every part <= 65535)."""
    _, minor, patch = (int(x) for x in app.split("."))
    return f"1.{minor}.{patch}.0"


def load_identity(path: Path = IDENTITY) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    for key in ("name", "publisher", "publisher_display"):
        if not str(data.get(key) or "").strip():
            raise SystemExit(f"{path.name}: {key} is empty")
    return data


def manifest(identity: dict, version: str) -> str:
    e = lambda s: escape(str(s), {'"': "&quot;"})  # noqa: E731
    return f"""<?xml version="1.0" encoding="utf-8"?>
<Package
  xmlns="http://schemas.microsoft.com/appx/manifest/foundation/windows10"
  xmlns:uap="http://schemas.microsoft.com/appx/manifest/uap/windows10"
  xmlns:desktop="http://schemas.microsoft.com/appx/manifest/desktop/windows10"
  xmlns:rescap="http://schemas.microsoft.com/appx/manifest/foundation/windows10/restrictedcapabilities"
  IgnorableNamespaces="uap desktop rescap">
  <Identity Name="{e(identity['name'])}" Publisher="{e(identity['publisher'])}" Version="{version}" ProcessorArchitecture="x64" />
  <Properties>
    <DisplayName>{e(DISPLAY)}</DisplayName>
    <PublisherDisplayName>{e(identity['publisher_display'])}</PublisherDisplayName>
    <Logo>Assets\\StoreLogo.png</Logo>
  </Properties>
  <Dependencies>
    <TargetDeviceFamily Name="Windows.Desktop" MinVersion="10.0.17763.0" MaxVersionTested="10.0.26100.0" />
  </Dependencies>
  <Resources>
    <Resource Language="ko-KR" />
  </Resources>
  <Applications>
    <Application Id="Helper" Executable="helper\\{NAME}.exe" EntryPoint="Windows.FullTrustApplication">
      <uap:VisualElements DisplayName="{e(DISPLAY)}" Description="{e(DESCRIPTION)}" BackgroundColor="transparent"
        Square150x150Logo="Assets\\Square150x150Logo.png" Square44x44Logo="Assets\\Square44x44Logo.png" />
      <Extensions>
        <desktop:Extension Category="windows.startupTask" Executable="helper\\{NAME}Startup.exe" EntryPoint="Windows.FullTrustApplication">
          <desktop:StartupTask TaskId="{NAME}Startup" Enabled="true" DisplayName="{e(DISPLAY)}" />
        </desktop:Extension>
      </Extensions>
    </Application>
  </Applications>
  <Capabilities>
    <Capability Name="internetClient" />
    <rescap:Capability Name="runFullTrust" />
  </Capabilities>
</Package>
"""


def draw_icon(size: int):
    from PIL import Image, ImageDraw, ImageFont

    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    r = max(2, size // 6)
    d.rounded_rectangle((0, 0, size - 1, size - 1), radius=r, fill=(31, 111, 235, 255))
    try:
        font = ImageFont.truetype("C:/Windows/Fonts/malgunbd.ttf", int(size * 0.58))
    except OSError:
        font = ImageFont.load_default()
    d.text((size / 2, size / 2), "문", fill=(255, 255, 255, 255), font=font, anchor="mm")
    return img


def write_assets(dest: Path) -> Path:
    dest.mkdir(parents=True, exist_ok=True)
    for name, size in ASSETS.items():
        draw_icon(size).save(dest / name)
    ico = WORK / f"{NAME}.ico"
    draw_icon(256).save(ico, sizes=[(16, 16), (32, 32), (48, 48), (256, 256)])
    return ico


def build_folder(ico: Path) -> Path:
    if not ensure_pyinstaller():
        raise SystemExit("pyinstaller install failed")
    dist = WORK / "dist"
    shutil.rmtree(dist, ignore_errors=True)
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm", "--onedir", "--noconsole",
        "--name", NAME,
        "--icon", str(ico),
        "--paths", str(ROOT / "scripts"),
        "--collect-submodules", "websockets",
        "--hidden-import", "helper_window",
        "--distpath", str(dist),
        "--workpath", str(WORK / "build"),
        "--specpath", str(WORK),
        str(ROOT / "scripts" / "helper_app.py"),
    ]
    rc = subprocess.run(cmd, cwd=ROOT).returncode
    folder = dist / NAME
    exe = folder / f"{NAME}.exe"
    if rc != 0 or not exe.is_file():
        raise SystemExit(f"pyinstaller failed (exit {rc})")
    shutil.copy2(exe, folder / f"{NAME}Startup.exe")
    return folder


def find_makeappx() -> Path:
    found = sorted(TOOLS.glob("bin/*/x64/makeappx.exe"))
    if found:
        return found[-1]
    TOOLS.mkdir(parents=True, exist_ok=True)
    pkg = TOOLS / "buildtools.nupkg"
    print("downloading Microsoft.Windows.SDK.BuildTools")
    with urllib.request.urlopen(NUGET_URL, timeout=300) as r, pkg.open("wb") as fh:
        shutil.copyfileobj(r, fh)
    with zipfile.ZipFile(pkg) as z:
        z.extractall(TOOLS)
    pkg.unlink()
    found = sorted(TOOLS.glob("bin/*/x64/makeappx.exe"))
    if not found:
        raise SystemExit("makeappx.exe not in the build tools package")
    return found[-1]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--layout-only", action="store_true")
    args = ap.parse_args()
    identity = load_identity()
    version = package_version(app_version())
    shutil.rmtree(LAYOUT, ignore_errors=True)
    LAYOUT.mkdir(parents=True)
    ico = write_assets(LAYOUT / "Assets")
    folder = build_folder(ico)
    shutil.copytree(folder, LAYOUT / "helper")
    (LAYOUT / "AppxManifest.xml").write_text(manifest(identity, version), encoding="utf-8")
    print(f"layout: {LAYOUT} (version {version})")
    if args.layout_only:
        return 0
    makeappx = find_makeappx()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    rc = subprocess.run([str(makeappx), "pack", "/d", str(LAYOUT), "/p", str(OUT), "/o"]).returncode
    if rc != 0 or not OUT.is_file():
        print(f"makeappx failed (exit {rc})")
        return 1
    print(f"msix: {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
