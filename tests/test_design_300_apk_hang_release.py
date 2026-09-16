"""design/300 — APK script must not wait forever on a hung flutter."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DESIGN = ROOT / "docs/design/300-apk-hang-release.md"
README = ROOT / "docs/design/README.md"
APK = ROOT / "scripts/build_release_apk.ps1"
GUARD = ROOT / ".cursor/rules/deploy-live-guard.mdc"


def test_design_300_locked() -> None:
    text = DESIGN.read_text(encoding="utf-8")
    assert "Status: **locked**" in text
    assert "GradleDaemon" in text
    assert "300 |" in README.read_text(encoding="utf-8")
    assert "design/300" in GUARD.read_text(encoding="utf-8")


def test_apk_script_releases_hang_and_waits_for_daemon() -> None:
    text = APK.read_text(encoding="utf-8")
    assert "design/300: failure log idle - stop hung flutter" in text
    assert "design/300: APK file stable - stop hung flutter" in text
    assert "Wait-GradleDaemonsGone" in text
    assert "GradleDaemon" in text
    assert "taskkill.exe" in text
    # Retry must wait for the daemon after --stop, not sleep-and-start.
    snap = text.split("function Clear-FlutterSnapshot", 1)[1].split("function ", 1)[0]
    assert "Wait-GradleDaemonsGone" in snap
    assert "Start-Sleep -Seconds 2" not in snap
