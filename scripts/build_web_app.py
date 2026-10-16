"""design/405 - build the Flutter web app for /app/ and place it where the server serves it.

usage: python scripts/build_web_app.py [--skip-build]

1. flutter build web --release --base-href /app/  (through scripts/flutter_any.cmd)
2. replace src/sentence_reading/web_app with mobile/build/web, minus canvaskit/
   (the loader fetches CanvasKit from Google's CDN) and .last_build_id.
3. check web_app/version.json against mobile/pubspec.yaml.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BUILD = ROOT / "mobile" / "build" / "web"
DEST = ROOT / "src" / "sentence_reading" / "web_app"
SKIP = {"canvaskit", ".last_build_id"}


def pubspec_version() -> str:
    text = (ROOT / "mobile" / "pubspec.yaml").read_text(encoding="utf-8")
    m = re.search(r"^version:\s*([0-9]+\.[0-9]+\.[0-9]+)", text, re.M)
    if not m:
        raise SystemExit("pubspec version not found")
    return m.group(1)


def web_app_version(dest: Path = DEST) -> str:
    try:
        return str(json.loads((dest / "version.json").read_text(encoding="utf-8")).get("version") or "")
    except (OSError, ValueError):
        return ""


def sync(build: Path = BUILD, dest: Path = DEST) -> int:
    if not (build / "index.html").is_file():
        raise SystemExit(f"{build} has no index.html")
    html = (build / "index.html").read_text(encoding="utf-8")
    if '<base href="/app/">' not in html:
        raise SystemExit("build was not made with --base-href /app/")
    if dest.exists():
        shutil.rmtree(dest)
    n = 0
    for src in build.rglob("*"):
        rel = src.relative_to(build)
        if rel.parts[0] in SKIP or not src.is_file():
            continue
        out = dest / rel
        out.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, out)
        n += 1
    return n


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-build", action="store_true")
    args = ap.parse_args()
    if not args.skip_build:
        rc = subprocess.call(
            [
                "cmd", "/c", str(ROOT / "scripts" / "flutter_any.cmd"),
                "build", "web", "--release", "--no-wasm-dry-run", "--base-href", "/app/",
            ],
            cwd=ROOT,
        )
        if rc != 0:
            print(f"flutter build web failed: exit {rc}")
            return rc
    n = sync()
    want, got = pubspec_version(), web_app_version()
    print(f"web_app files={n} version={got} pubspec={want}")
    if got != want:
        print("web_app version does not match pubspec")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
