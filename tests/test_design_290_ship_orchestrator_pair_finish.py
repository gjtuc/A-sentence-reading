"""design/290 — ship orchestrator + pair finish worker."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DESIGN = ROOT / "docs/design/290-ship-orchestrator-pair-finish.md"
README = ROOT / "docs/design/README.md"
PAIR = ROOT / "scripts/deploy_cloud_run_pair.sh"
SHIP_PS1 = ROOT / "scripts/ship_cloud_pair.ps1"
SHIP_SH = ROOT / "scripts/ship_release.sh"
CHECK = ROOT / "scripts/check_api_worker_images_match.py"


def test_design_290_locked() -> None:
    text = DESIGN.read_text(encoding="utf-8")
    assert "Status: **locked" in text
    assert "settle" in text.lower()
    assert "ship_cloud_pair" in text
    assert "image" in text.lower()


def test_scripts_290() -> None:
    assert "290-ship-orchestrator-pair-finish.md" in README.read_text(encoding="utf-8")
    pair = PAIR.read_text(encoding="utf-8")
    assert "ASR_PAIR_SETTLE_SEC" in pair or "SETTLE_SEC" in pair
    assert "phase=b" in pair
    assert "pair_ok=1" in pair
    assert "worker_image" in pair or "WORKER_SERVICE" in pair
    assert "ship_release.sh" in SHIP_PS1.read_text(encoding="utf-8")
    release = SHIP_SH.read_text(encoding="utf-8")
    assert "deploy_cloud_run_pair.sh" in release
    assert "verify_live_status" in release
    assert "ASR_SHIP_ALLOW_PARALLEL_APK" in release
    assert CHECK.is_file()
    assert "mismatch" in CHECK.read_text(encoding="utf-8")


def test_parallel_apk_check_asks_the_build_instead_of_the_process_list() -> None:
    """design/369 — the refusal reads a PID the build wrote, not a name it guessed.

    Two earlier versions scanned the process list and both refused every ship:
    image names matched the IDE Dart analysis server, and `GradleDaemon` matched
    the idle daemon a finished build leaves behind for hours.
    """
    from sentence_reading.llm.evidence_floor import code_only

    # Comments name the two guesses that failed, so only code is searched here.
    release = code_only(SHIP_SH.read_text(encoding="utf-8"), ".sh")
    assert ".cache/apk_build.lock" in release
    assert "Get-Process -Id" in release
    # Every process-list guess has to be gone, or the old refusal comes back.
    for guess in ("Win32_Process", "GradleDaemon", "GradleWrapperMain", "tasklist"):
        assert guess not in release, f"still guessing from {guess}"

    build = (ROOT / "scripts" / "build_release_apk.ps1").read_text(encoding="utf-8")
    assert "New-ApkBuildLock" in build
    assert "Remove-ApkBuildLock" in build
    # A crashed build must not block ships forever, so a dead PID is ignored.
    assert "Test-ApkBuildLockLive" in build
