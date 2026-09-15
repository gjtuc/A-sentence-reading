"""design/292 — live API must not be serving worker role."""
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--url",
        default="https://asr-sentence-reading-984608876300.asia-northeast3.run.app/api/status",
    )
    p.add_argument("--expect-version", default="", help="optional exact version")
    args = p.parse_args()
    try:
        with urllib.request.urlopen(args.url, timeout=45) as r:
            raw = r.read().decode("utf-8", errors="replace")
            data = json.loads(raw)
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as e:
        print(f"ok=false error=fetch:{e}", file=sys.stderr)
        return 1

    role = str(data.get("service_role") or "").strip().lower()
    ver = str(data.get("version") or "").strip()
    print(f"service_role={role or 'api_default'} version={ver or '-'}")

    if role == "worker":
        print("ok=false code=api_serving_worker_role", file=sys.stderr)
        return 2
    if not ver:
        print("ok=false code=api_version_missing", file=sys.stderr)
        return 2
    if args.expect_version and ver != args.expect_version:
        print(
            f"ok=false code=version_mismatch got={ver} want={args.expect_version}",
            file=sys.stderr,
        )
        return 2
    print("ok=true code=api_role_ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
