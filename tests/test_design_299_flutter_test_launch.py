"""design/299 — flutter test launcher must not use $env:ProgramFiles(x86)."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DESIGN = ROOT / "docs/design/299-flutter-test-launch.md"
README = ROOT / "docs/design/README.md"
CMD = ROOT / "scripts/flutter_test.cmd"
PS1 = ROOT / "scripts/flutter_test.ps1"
GUARD = ROOT / ".cursor/rules/deploy-live-guard.mdc"


def test_design_299_locked() -> None:
    text = DESIGN.read_text(encoding="utf-8")
    assert "Status: **locked**" in text
    assert "flutter_test.cmd" in text
    assert "299 |" in README.read_text(encoding="utf-8")
    assert "flutter_test.cmd" in GUARD.read_text(encoding="utf-8")


def test_flutter_cmd_bypasses_execution_policy() -> None:
    text = CMD.read_text(encoding="utf-8")
    assert "ExecutionPolicy Bypass" in text
    assert "flutter_test.ps1" in text
    assert "$env:" not in text
    assert "bash" not in text.lower()


def test_flutter_ps1_sets_program_files_without_env_drive() -> None:
    text = PS1.read_text(encoding="utf-8")
    assert "SetEnvironmentVariable" in text
    assert "ProgramFiles(x86)" in text
    assert "flutter test" in text
    assert "$env:" not in text
    assert "Set-Location" in text
