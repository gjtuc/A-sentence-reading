"""design/296 — Windows commit must not go through bash heredoc."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DESIGN = ROOT / "docs/design/296-windows-commit-shell.md"
README = ROOT / "docs/design/README.md"
COMMIT = ROOT / "scripts/git_commit.ps1"
SHIP_PS = ROOT / "scripts/ship_cloud_pair.ps1"
GUARD = ROOT / ".cursor/rules/deploy-live-guard.mdc"


def test_design_296_locked() -> None:
    text = DESIGN.read_text(encoding="utf-8")
    assert "Status: **locked**" in text
    assert "git_commit.ps1" in text
    assert "296 |" in README.read_text(encoding="utf-8")


def test_commit_script_has_no_bash_heredoc() -> None:
    text = COMMIT.read_text(encoding="utf-8")
    assert "git commit -m" in text
    assert "design/296" in text
    assert "bash" not in text.lower()
    assert "<<EOF" not in text
    assert "-lc" not in text


def test_ship_wrapper_pins_git_bash() -> None:
    text = SHIP_PS.read_text(encoding="utf-8")
    assert r"C:\Program Files\Git\bin\bash.exe" in text
    assert "bash -lc" not in text.split("Git\\bin\\bash.exe")[0]


def test_deploy_guard_points_at_commit_script() -> None:
    text = GUARD.read_text(encoding="utf-8")
    assert "git_commit.ps1" in text
    assert "WSL" in text
