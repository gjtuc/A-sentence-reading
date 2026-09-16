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
    assert 'set "' in text
    assert "flutter build apk --release" in text
    assert text.find('set "') < text.find("flutter build apk --release")
    assert "$env:ProgramFiles" not in text
    assert "$env:'ProgramFiles" not in text


def test_ship_wrapper_verifies_instead_of_redeploying() -> None:
    wrapper = (ROOT / "scripts/ship_cloud_pair.ps1").read_text(encoding="utf-8")
    assert "stdbuf -oL -eL" in wrapper
    assert "WindowStyle Hidden" not in wrapper
    assert "& $bash -lc" in wrapper
    bash_at = wrapper.find("& $bash -lc")
    assert wrapper.rfind('$ErrorActionPreference = "Continue"', 0, bash_at) != -1
    assert "ship_release OK" in wrapper
    assert "verify only, no second deploy" in wrapper
    assert "verify_live_status.py" in wrapper
    stall = wrapper.split("verify only, no second deploy", 1)[1]
    assert "ship_release.sh" not in stall


def test_pytest_launcher_pins_this_repo() -> None:
    cmd = PYTEST_CMD.read_text(encoding="utf-8")
    ps1 = PYTEST_PS1.read_text(encoding="utf-8")
    assert "ExecutionPolicy Bypass" in cmd
    assert "pytest.ps1" in cmd
    assert "PYTHONPATH" in ps1
    assert "Set-Location" in ps1
    assert "sentence_reading" in CONFTEST.read_text(encoding="utf-8")


def test_design_305_windows_push_then_apk_install() -> None:
    wrapper = (ROOT / "scripts/ship_cloud_pair.ps1").read_text(encoding="utf-8")
    ship = SHIP.read_text(encoding="utf-8")
    apk = APK.read_text(encoding="utf-8")
    rule = RULE.read_text(encoding="utf-8")
    assert "Windows git.exe not found" in wrapper
    assert "Windows git push origin main before bash ship" in wrapper
    assert wrapper.find("Windows git push origin main") < wrapper.find("& $bash -lc")
    assert "ASR_SHIP_WINDOWS_PUSHED=1" in wrapper
    assert "ASR_SHIP_WINDOWS_PUSHED" in ship
    assert "Windows git.exe push" in ship
    assert "git push --force" not in ship
    assert "adb install -r" in apk
    assert "installed versionName=" in apk
    assert "SkipInstall" in apk
    assert "until that ship has finished" in rule
