"""design/287 — deploy/APK wall-clock guards present."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DESIGN = ROOT / "docs/design/287-deploy-apk-wallclock-guards.md"
README = ROOT / "docs/design/README.md"
GRADLE = ROOT / "mobile/android/gradle.properties"
DEPLOY = ROOT / "scripts/deploy_cloud_run.sh"
WORKER = ROOT / "scripts/deploy_cloud_run_worker.sh"
PAIR = ROOT / "scripts/deploy_cloud_run_pair.sh"
APK_PS1 = ROOT / "scripts/build_release_apk.ps1"


def test_design_287_locked() -> None:
    text = DESIGN.read_text(encoding="utf-8")
    assert "Status: **locked" in text
    assert "Could not close incremental caches" in text
    assert "ABORTED: Conflict" in text
    assert "D4" in text and "ASR_DEPLOY_IMAGE" in text
    assert "D5" in text and "PUB_CACHE" in text


def test_readme_and_files_287() -> None:
    assert "287-deploy-apk-wallclock-guards.md" in README.read_text(encoding="utf-8")
    gp = GRADLE.read_text(encoding="utf-8")
    assert "kotlin.incremental=false" in gp
    assert "design/287" in gp
    dep = DEPLOY.read_text(encoding="utf-8")
    assert "ASR_DEPLOY_CONFLICT_RETRIES" in dep
    assert "Conflict for resource" in dep
    assert "ASR_DEPLOY_IMAGE" in dep
    assert "--image" in dep
    assert "ASR_DEPLOY_CONFLICT_RETRIES" in WORKER.read_text(encoding="utf-8")
    pair = PAIR.read_text(encoding="utf-8")
    assert "design/287" in pair
    assert "ASR_DEPLOY_IMAGE" in pair
    assert "deploy_cloud_run_worker.sh" in pair
    apk = APK_PS1.read_text(encoding="utf-8")
    assert "design/287" in apk
    assert "Could not close incremental caches" in apk
    assert "PUB_CACHE" in apk
    assert "GRADLE_USER_HOME" in apk
    assert ".cache\\apk-tooling" in apk or ".cache/apk-tooling" in apk
