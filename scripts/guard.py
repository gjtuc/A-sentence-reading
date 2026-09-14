#!/usr/bin/env python3
"""design/255 Phase 1A — thin CLI wrapper over existing deploy guards.

Does not reimplement logic; fail-closed exit codes match the wrapped scripts.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _run(script: str, extra: list[str] | None = None) -> int:
    cmd = [sys.executable, str(ROOT / "scripts" / script), *(extra or [])]
    proc = subprocess.run(cmd, cwd=str(ROOT))
    return int(proc.returncode)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="ASR unified guard (design/255)")
    p.add_argument(
        "command",
        choices=("freshness", "floor", "pre-deploy", "all"),
        help="Which guard to run",
    )
    p.add_argument(
        "--allow-same-version",
        action="store_true",
        help="Forward to pre_deploy_guard.py",
    )
    args = p.parse_args(argv)

    if args.command == "freshness":
        return _run("session_freshness_guard.py")
    if args.command == "floor":
        return _run("check_evidence_floor.py")
    if args.command == "pre-deploy":
        extra = ["--allow-same-version"] if args.allow_same_version else []
        return _run("pre_deploy_guard.py", extra)
    # all — stop on first failure
    for step, script, extra in (
        ("freshness", "session_freshness_guard.py", []),
        ("floor", "check_evidence_floor.py", []),
        (
            "pre-deploy",
            "pre_deploy_guard.py",
            ["--allow-same-version"] if args.allow_same_version else [],
        ),
    ):
        code = _run(script, extra)
        if code != 0:
            print(f"guard.py: {step} failed with exit {code}", file=sys.stderr)
            return code
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
