"""design/291 — staged source · bash ship · APK cache fallback."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DESIGN = ROOT / "docs/design/291-ship-staged-source-bash-apk.md"
README = ROOT / "docs/design/README.md"
PAIR = ROOT / "scripts/deploy_cloud_run_pair.sh"
DEPLOY = ROOT / "scripts/deploy_cloud_run.sh"
STAGE = ROOT / "scripts/stage_git_archive_for_ship.sh"
SHIP = ROOT / "scripts/ship_release.sh"
PS1 = ROOT / "scripts/ship_cloud_pair.ps1"
APK = ROOT / "scripts/build_release_apk.ps1"
CHECK = ROOT / "scripts/check_api_worker_images_match.py"


def test_design_291_locked() -> None:
    text = DESIGN.read_text(encoding="utf-8")
    assert "Status: **locked" in text
    assert "Staged" in text or "staged" in text
    assert "ship_release" in text
    assert "SameDriveCache" in text or "kernel_snapshot" in text


def test_scripts_291() -> None:
    assert "291-ship-staged-source-bash-apk.md" in README.read_text(encoding="utf-8")
    assert STAGE.is_file()
    assert "archive HEAD" in STAGE.read_text(encoding="utf-8")
    pair = PAIR.read_text(encoding="utf-8")
    assert "ASR_PAIR_STAGED_SOURCE" in pair
    assert "stage_git_archive_for_ship" in pair
    assert "ASR_DEPLOY_SOURCE_DIR" in DEPLOY.read_text(encoding="utf-8")
    ship = SHIP.read_text(encoding="utf-8")
    assert "deploy_cloud_run_pair.sh" in ship
    assert "verify_live_status" in ship
    ps1 = PS1.read_text(encoding="utf-8")
    assert "ship_release.sh" in ps1
    assert "deploy_cloud_run_pair.sh" not in ps1 or "ship_release" in ps1
    apk = APK.read_text(encoding="utf-8")
    assert "SameDriveCache" in apk
    assert "kernel_snapshot" in apk
    assert "Disable-SameDriveCache" in apk
    assert "_gcloud_bin" in CHECK.read_text(encoding="utf-8")
