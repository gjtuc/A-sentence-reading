"""design/290/291 — API and worker images match, or the worker is a registry copy of the same release."""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path


def images_compatible(
    api: str,
    worker: str,
    api_ver: str,
    worker_ver: str,
    expect: str = "",
) -> bool:
    if api and api == worker:
        return True
    # Cloud Run copies the API image into the worker repo and changes the digest.
    if "/asr-sentence-reading-worker@" not in worker:
        return False
    if not api_ver or api_ver != worker_ver:
        return False
    if expect and api_ver != expect:
        return False
    return True


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


def _release_version(service: str, region: str) -> str:
    out = subprocess.check_output(
        [
            _gcloud_bin(),
            "run",
            "services",
            "describe",
            service,
            "--region",
            region,
            "--format=json(spec.template.spec.containers[0].env)",
        ],
        text=True,
        errors="replace",
    )
    data = json.loads(out or "{}")
    containers = (
        ((data.get("spec") or {}).get("template") or {}).get("spec") or {}
    ).get("containers") or []
    env = containers[0].get("env") if containers else []
    for item in env or []:
        if str(item.get("name") or "") == "ASR_RELEASE_VERSION":
            return str(item.get("value") or "").strip()
    return ""


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--region", default="asia-northeast3")
    p.add_argument("--api", default="asr-sentence-reading")
    p.add_argument("--worker", default="asr-sentence-reading-worker")
    p.add_argument("--expect-version", default="")
    args = p.parse_args()
    api = _image(args.api, args.region)
    worker = _image(args.worker, args.region)
    api_ver = _release_version(args.api, args.region)
    worker_ver = _release_version(args.worker, args.region)
    print(f"api={api}")
    print(f"worker={worker}")
    print(f"api_release={api_ver or '-'}")
    print(f"worker_release={worker_ver or '-'}")
    if images_compatible(api, worker, api_ver, worker_ver, args.expect_version):
        print("match=1")
        return 0
    print("mismatch", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
