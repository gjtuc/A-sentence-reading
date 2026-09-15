"""design/290 — ship orchestrator + pair finish worker."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DESIGN = ROOT / "docs/design/290-ship-orchestrator-pair-finish.md"
README = ROOT / "docs/design/README.md"
PAIR = ROOT / "scripts/deploy_cloud_run_pair.sh"
SHIP = ROOT / "scripts/ship_cloud_pair.ps1"
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
    ship = SHIP.read_text(encoding="utf-8")
    assert "deploy_cloud_run_pair.sh" in ship
    assert "verify_live_status" in ship
    assert "ASR_SHIP_ALLOW_PARALLEL_APK" in ship
    assert CHECK.is_file()
    assert "mismatch" in CHECK.read_text(encoding="utf-8")
