"""design/316 — GitHub CD pair; solo worker CD retired."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DESIGN = ROOT / "docs/design/316-github-cd-pair.md"
README = ROOT / "docs/design/README.md"
PAIR = ROOT / "scripts/deploy_cloud_run_pair.sh"
CAP = ROOT / "scripts/deploy_capacity_profile.sh"
API_WF = ROOT / ".github/workflows/deploy-cloud-run.yml"
WORKER_WF = ROOT / ".github/workflows/deploy-cloud-run-worker.yml"


def test_design_316_locked() -> None:
    text = DESIGN.read_text(encoding="utf-8")
    assert "Status: **locked" in text
    assert "deploy_cloud_run_pair.sh" in text
    assert "asr-cloud-pair" in text


def test_capacity_worker_hop_uses_pair() -> None:
    cap = CAP.read_text(encoding="utf-8")
    assert "deploy_cloud_run_pair.sh" in cap
    assert "design/316" in cap
    # Must not rebuild the worker from source after the API hop.
    after = cap.split("DEPLOY_WORKER")[1]
    assert "ASR_SERVICE_ROLE=worker" not in after
    assert "bash scripts/deploy_cloud_run.sh" not in after.split("SCALE_WORKER_MIN")[0]


def test_cd_workflows_share_pair_group() -> None:
    api = API_WF.read_text(encoding="utf-8")
    worker = WORKER_WF.read_text(encoding="utf-8")
    assert "asr-cloud-pair" in api
    assert "asr-cloud-pair" in worker
    assert "deploy_cloud_run_pair.sh" in api
    assert "src/sentence_reading/worker/**" in api
    assert "bash scripts/deploy_cloud_run_worker.sh" not in worker
    assert "setup-gcloud" not in worker
    assert "google-github-actions/auth" not in worker
    assert "This job does not call gcloud." in worker


def test_readme_and_pair_script_316() -> None:
    assert "316-github-cd-pair.md" in README.read_text(encoding="utf-8")
    assert PAIR.is_file()
    assert "check_api_worker_images_match.py" in PAIR.read_text(encoding="utf-8")
