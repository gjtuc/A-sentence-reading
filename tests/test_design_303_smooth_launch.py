"""design/303 — push before ship, APK catalog, pytest pins this tree."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DESIGN = ROOT / "docs/design/303-smooth-ship-launch.md"
README = ROOT / "docs/design/README.md"
SHIP = ROOT / "scripts/ship_release.sh"
APK = ROOT / "scripts/build_release_apk.ps1"
PYTEST_CMD = ROOT / "scripts/pytest.cmd"
PYTEST_PS1 = ROOT / "scripts/pytest.ps1"
CONFTEST = ROOT / "tests/conftest.py"
RULE = ROOT / ".cursor/rules/smooth-ship-launch.mdc"


def test_design_303_locked() -> None:
    text = DESIGN.read_text(encoding="utf-8")
    assert "Status: **locked**" in text
    assert "303 |" in README.read_text(encoding="utf-8")
    assert "pytest.cmd" in RULE.read_text(encoding="utf-8")


def test_ship_pushes_fast_forward_before_deploy() -> None:
    text = SHIP.read_text(encoding="utf-8")
    assert "design/303: push origin main before ship" in text
    assert "git push origin main" in text
    assert "git push --force" not in text
    assert "ASR_SHIP_ALLOW_UNPUSHED" in text
    assert "pull --ff-only first" in text


def test_apk_sets_program_files_without_env_drive() -> None:
    text = APK.read_text(encoding="utf-8")
    assert "SetEnvironmentVariable" in text
    assert "ProgramFiles(x86)" in text
    assert "$env:ProgramFiles" not in text
    assert "$env:'ProgramFiles" not in text


def test_pytest_launcher_pins_this_repo() -> None:
    cmd = PYTEST_CMD.read_text(encoding="utf-8")
    ps1 = PYTEST_PS1.read_text(encoding="utf-8")
    assert "ExecutionPolicy Bypass" in cmd
    assert "pytest.ps1" in cmd
    assert "PYTHONPATH" in ps1
    assert "Set-Location" in ps1
    assert "sentence_reading" in CONFTEST.read_text(encoding="utf-8")
