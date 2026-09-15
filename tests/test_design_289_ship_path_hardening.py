"""design/289 — ship path hardening present."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DESIGN = ROOT / "docs/design/289-ship-path-hardening.md"
README = ROOT / "docs/design/README.md"
DEPLOY = ROOT / "scripts/deploy_cloud_run.sh"
PAIR = ROOT / "scripts/deploy_cloud_run_pair.sh"
APK = ROOT / "scripts/build_release_apk.ps1"


def test_design_289_locked() -> None:
    text = DESIGN.read_text(encoding="utf-8")
    assert "Status: **locked" in text
    assert "PermissionError" in text
    assert "pair resume" in text.lower() or "S2" in text
    assert "artifact" in text.lower()


def test_readme_and_scripts_289() -> None:
    assert "289-ship-path-hardening.md" in README.read_text(encoding="utf-8")
    dep = DEPLOY.read_text(encoding="utf-8")
    assert "PermissionError" in dep
    assert "gcloud crashed" in dep
    assert "Errno 13" in dep
    pair = PAIR.read_text(encoding="utf-8")
    assert "289" in pair
    assert "_live_matches_head" in pair or "live already at HEAD" in pair
    assert "deploy_cloud_run_worker.sh" in pair
    apk = APK.read_text(encoding="utf-8")
    assert "289" in apk
    assert "Test-FreshApk" in apk or "fresh APK" in apk
    assert "WarmCaches" in apk
