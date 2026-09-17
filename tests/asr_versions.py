"""Version helpers so design tests pin a floor instead of a literal.

WHY: design tests used to assert `st["version"] == "0.3.156"` to record which
release a feature shipped in. Every later release broke them, and because CI
could not even collect the suite (see `conftest._interpreter_package_dirs`)
nobody noticed until 224 of them failed at once. A floor keeps the same intent
— "this behaviour exists from 0.3.156 onward" — without rotting.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP_PY = ROOT / "src" / "sentence_reading" / "api" / "app.py"

_VERSION_RE = re.compile(r'version\s*=\s*"(\d+\.\d+\.\d+)"')


def app_version() -> str:
    """The version this checkout serves from `/api/status`."""
    text = APP_PY.read_text(encoding="utf-8")
    match = _VERSION_RE.search(text)
    if match is None:
        raise AssertionError(f"no version literal in {APP_PY}")
    return match.group(1)


def as_tuple(version: str) -> tuple[int, ...]:
    parts: list[int] = []
    for chunk in version.strip().split("."):
        digits = re.match(r"\d+", chunk)
        parts.append(int(digits.group(0)) if digits else 0)
    while len(parts) < 3:
        parts.append(0)
    return tuple(parts[:3])


def at_least(actual: str, floor: str) -> bool:
    return as_tuple(actual) >= as_tuple(floor)


def assert_at_least(actual: str, floor: str) -> None:
    """Fail when `actual` predates the release that introduced the behaviour."""
    assert at_least(actual, floor), f"version {actual!r} is below floor {floor!r}"
