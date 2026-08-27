"""Prevent display sleep by simulating F15 every 3 minutes (Windows only)."""

from __future__ import annotations

import argparse
import ctypes
import sys
import time

DEFAULT_INTERVAL_SEC = 180
VK_F15 = 0x7E
KEYEVENTF_KEYUP = 0x0002


def press_f15() -> None:
    user32 = ctypes.windll.user32
    user32.keybd_event(VK_F15, 0, 0, 0)
    user32.keybd_event(VK_F15, 0, KEYEVENTF_KEYUP, 0)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Keep screen awake with periodic F15 keypress")
    parser.add_argument(
        "--interval",
        type=int,
        default=DEFAULT_INTERVAL_SEC,
        help="seconds between keypresses (default: 180)",
    )
    args = parser.parse_args(argv)

    if sys.platform != "win32":
        print("keep_screen_awake: Windows only", file=sys.stderr)
        return 1
    if args.interval < 1:
        print("keep_screen_awake: interval must be >= 1", file=sys.stderr)
        return 1

    print(
        f"keep_screen_awake: F15 every {args.interval}s - Ctrl+C to stop",
        flush=True,
    )
    while True:
        press_f15()
        time.sleep(args.interval)


if __name__ == "__main__":
    raise SystemExit(main())
