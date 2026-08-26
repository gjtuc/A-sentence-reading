"""
design/138 — local-server autostart removed.

Product path is Live (Cloud Run) + device APK only.
This module only **unregisters** any leftover Windows scheduled task.
``register`` / ``ensure`` refuse (fail-closed — do not start 127.0.0.1 uvicorn).
"""

from __future__ import annotations

import argparse
import subprocess
import sys

TASK_NAME = "A-sentence-reading Ensure Server"

_REMOVED_MSG = (
    "design/138: local-server autostart removed. "
    "Use Live Cloud Run + device APK. "
    "To clear an old task: python -m sentence_reading.autostart unregister"
)


def task_registered() -> bool:
    if sys.platform != "win32":
        return False
    proc = subprocess.run(
        ["schtasks", "/Query", "/TN", TASK_NAME],
        capture_output=True,
        text=True,
        check=False,
    )
    return proc.returncode == 0


def register_task(*, quiet: bool = False) -> int:
    # WHY: never re-bind Windows login to a local uvicorn after design/138.
    if not quiet:
        print(_REMOVED_MSG, file=sys.stderr)
    return 1


def ensure_server() -> int:
    print(_REMOVED_MSG, file=sys.stderr)
    return 1


def ensure_registered(*, quiet: bool = True) -> None:
    """Legacy lifespan hook — no longer registers; best-effort unregister."""
    unregister_task(quiet=quiet)


def unregister_task(*, quiet: bool = False) -> int:
    """Remove leftover Ensure Server task if present."""
    if sys.platform != "win32":
        return 0
    if not task_registered():
        if not quiet:
            print(f"Not registered: {TASK_NAME}")
        return 0
    proc = subprocess.run(
        ["schtasks", "/Delete", "/TN", TASK_NAME, "/F"],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0 and not quiet:
        print((proc.stderr or proc.stdout or "delete failed").strip(), file=sys.stderr)
        return 1
    if not quiet:
        print(f"Unregistered: {TASK_NAME}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="sentence-reading-autostart")
    parser.add_argument(
        "command",
        nargs="?",
        default="status",
        choices=("register", "ensure", "unregister", "status"),
    )
    args = parser.parse_args(argv)
    if args.command == "register":
        return register_task(quiet=False)
    if args.command == "ensure":
        print(_REMOVED_MSG, file=sys.stderr)
        return 1
    if args.command == "unregister":
        return unregister_task(quiet=False)
    # status
    if sys.platform != "win32":
        print("status: non-Windows — no scheduled task")
        return 0
    print(
        f"status: task={TASK_NAME!r} registered={task_registered()} "
        f"(autostart disabled · design/138)"
    )
    return 0


def entrypoint() -> None:
    raise SystemExit(main())


if __name__ == "__main__":
    entrypoint()
