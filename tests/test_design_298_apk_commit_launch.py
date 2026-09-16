"""design/298 — commit cmd launcher and APK snapshot retry."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DESIGN = ROOT / "docs/design/298-apk-commit-launch.md"
README = ROOT / "docs/design/README.md"
CMD = ROOT / "scripts/git_commit.cmd"
APK = ROOT / "scripts/build_release_apk.ps1"
GUARD = ROOT / ".cursor/rules/deploy-live-guard.mdc"


def test_design_298_locked() -> None:
    text = DESIGN.read_text(encoding="utf-8")
    assert "Status: **locked**" in text
    assert "git_commit.cmd" in text
    assert "298 |" in README.read_text(encoding="utf-8")
    assert "git_commit.cmd" in GUARD.read_text(encoding="utf-8")


def test_commit_cmd_bypasses_execution_policy() -> None:
    text = CMD.read_text(encoding="utf-8")
    assert "ExecutionPolicy Bypass" in text
    assert "git_commit.ps1" in text
    assert "bash" not in text.lower()


def test_apk_script_cmd_and_snapshot_retry() -> None:
    text = APK.read_text(encoding="utf-8")
    assert "cmd /c" in text
    assert "flutter build apk --release" in text
    assert "Test-ApkBuildAlreadyRunning" in text
    assert "design/298: refuse APK build" in text
    assert "Clear-FlutterSnapshot" in text
    assert "Invalid depfile" in text
    # Default-cache retry must not be gated on SameDrive.
    retry = text.split("design/298: snapshot or compile fail", 1)[1]
    assert "UsedSameDrive" not in retry.split("design/291", 1)[0]
