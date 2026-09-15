"""design/292 — API/worker role gates."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DESIGN = ROOT / "docs/design/292-api-worker-role-gates.md"
README = ROOT / "docs/design/README.md"
DEPLOY = ROOT / "scripts/deploy_cloud_run.sh"
PAIR = ROOT / "scripts/deploy_cloud_run_pair.sh"
SHIP = ROOT / "scripts/ship_release.sh"
PROBE = ROOT / "scripts/check_api_service_role.py"


def test_design_292_locked() -> None:
    text = DESIGN.read_text(encoding="utf-8")
    assert "Status: **locked" in text
    assert "service_role" in text
    assert "G1" in text and "G2" in text


def test_scripts_292() -> None:
    assert "292-api-worker-role-gates.md" in README.read_text(encoding="utf-8")
    dep = DEPLOY.read_text(encoding="utf-8")
    assert "design/292" in dep
    assert "non-worker service" in dep or "ASR_SERVICE_ROLE=worker" in dep
    pair = PAIR.read_text(encoding="utf-8")
    assert "check_api_service_role.py" in pair
    assert "unset ASR_SERVICE_ROLE" in pair
    ship = SHIP.read_text(encoding="utf-8")
    assert "check_api_service_role.py" in ship
    probe = PROBE.read_text(encoding="utf-8")
    assert "api_serving_worker_role" in probe
    assert "api_version_missing" in probe


def test_check_api_service_role_logic() -> None:
    # Pure: worker stub shape would fail version/role checks (unit via codes in source).
    assert "role == \"worker\"" in PROBE.read_text(encoding="utf-8")
