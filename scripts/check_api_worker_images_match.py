"""design/290/291 — API and worker Cloud Run images must match."""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path


def _gcloud_bin() -> str:
    found = shutil.which("gcloud") or shutil.which("gcloud.cmd")
    if found:
        return found
    candidates = [
        Path(os.environ.get("LOCALAPPDATA", ""))
        / "Google"
        / "Cloud SDK"
        / "google-cloud-sdk"
        / "bin"
        / "gcloud.cmd",
        Path(r"C:\Program Files (x86)\Google\Cloud SDK\google-cloud-sdk\bin\gcloud.cmd"),
        Path(r"C:\Program Files\Google\Cloud SDK\google-cloud-sdk\bin\gcloud.cmd"),
    ]
    for p in candidates:
        if p.is_file():
            return str(p)
    raise FileNotFoundError("gcloud not found on PATH or common install locations")


def _image(service: str, region: str) -> str:
    out = subprocess.check_output(
        [
            _gcloud_bin(),
            "run",
            "services",
            "describe",
            service,
            "--region",
            region,
            "--format=value(spec.template.spec.containers[0].image)",
        ],
        text=True,
        errors="replace",
    )
    return (out or "").strip()


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--region", default="asia-northeast3")
    p.add_argument("--api", default="asr-sentence-reading")
    p.add_argument("--worker", default="asr-sentence-reading-worker")
    args = p.parse_args()
    api = _image(args.api, args.region)
    worker = _image(args.worker, args.region)
    print(f"api={api}")
    print(f"worker={worker}")
    if not api or api != worker:
        print("mismatch", file=sys.stderr)
        return 1
    print("match=1")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
