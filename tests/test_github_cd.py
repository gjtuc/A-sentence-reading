"""GitHub CI/CD 계약 (0.2.33 · design/32)."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[1]
CI = ROOT / ".github" / "workflows" / "ci.yml"
DEPLOY = ROOT / ".github" / "workflows" / "deploy-cloud-run.yml"
DESIGN = ROOT / "docs" / "design" / "32-github-cd.md"
SCRIPT = ROOT / "scripts" / "deploy_cloud_run.sh"


def _git_bash() -> str:
    """Windows 는 system32\\bash(WSL 스텁)를 피하고 Git Bash 를 쓴다."""
    env = (os.environ.get("GIT_BASH") or "").strip()
    candidates = [
        env,
        r"C:\Program Files\Git\bin\bash.exe",
        r"C:\Program Files (x86)\Git\bin\bash.exe",
        "/usr/bin/bash",
        "bash",
    ]
    for c in candidates:
        if not c:
            continue
        if c in {"bash", "/usr/bin/bash"} or Path(c).is_file():
            return c
    return "bash"


def _run_deploy(env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    merged = {**os.environ, **env}
    return subprocess.run(
        [_git_bash(), str(SCRIPT)],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
        env=merged,
    )


def test_workflow_files_parse_and_gate() -> None:
    ci = yaml.safe_load(CI.read_text(encoding="utf-8"))
    assert ci["name"] == "CI"
    assert "pytest" in str(ci["jobs"])
    deploy = yaml.safe_load(DEPLOY.read_text(encoding="utf-8"))
    assert deploy["name"] == "Deploy Cloud Run"
    # WHY: 기본 off — secrets 없어도 main CI 가 빨개지지 않음
    assert "ASR_CD_ENABLED" in str(deploy["jobs"]["deploy"].get("if", ""))
    assert "google-github-actions/auth@v2" in DEPLOY.read_text(encoding="utf-8")
    design = DESIGN.read_text(encoding="utf-8")
    assert "0.2.33" in design
    assert "ASR_CD_ENABLED" in design
    assert "GCP_SA_KEY" in design


def test_deploy_dry_run_ok() -> None:
    # WHY: gcloud 없어도 dry-run 은 0 (design/32).
    r = _run_deploy(
        {
            "ASR_CD_DRY_RUN": "1",
            "ASR_GOOGLE_CLIENT_ID": "cid",
            "ASR_AUTH_SECRET": "sec",
            "GEMINI_API_KEY": "key",
        }
    )
    assert r.returncode == 0, (r.stdout, r.stderr)
    assert "dry-run:" in r.stdout


def test_deploy_missing_env_fails() -> None:
    # edge: 빈 CLIENT_ID → :? 로 비0
    r = _run_deploy(
        {
            "ASR_CD_DRY_RUN": "1",
            "ASR_GOOGLE_CLIENT_ID": "",
            "ASR_AUTH_SECRET": "x",
            "GEMINI_API_KEY": "y",
        }
    )
    assert r.returncode != 0


@pytest.mark.skipif(sys.platform != "win32", reason="PATH isolation is for Win gcloud miss")
def test_deploy_dry_run_without_gcloud_on_path(tmp_path: Path) -> None:
    # edge: PATH 에 gcloud 없어도 dry-run 성공 (Git Bash 절대경로)
    git_bin = Path(r"C:\Program Files\Git\bin")
    path = os.pathsep.join(
        [
            str(tmp_path),
            str(git_bin) if git_bin.is_dir() else "",
            str(git_bin.parent / "usr" / "bin") if git_bin.is_dir() else "",
        ]
    )
    r = _run_deploy(
        {
            "PATH": path,
            "ASR_CD_DRY_RUN": "1",
            "ASR_GOOGLE_CLIENT_ID": "cid",
            "ASR_AUTH_SECRET": "sec",
            "GEMINI_API_KEY": "key",
        }
    )
    assert r.returncode == 0, (r.stdout, r.stderr)
    assert "dry-run:" in r.stdout


def test_status_github_cd_flag() -> None:
    from fastapi.testclient import TestClient

    from sentence_reading.api.app import app

    st = TestClient(app).get("/api/status").json()
    assert st["version"] == "0.2.33"
    assert st.get("github_cd") is True


def test_no_secrets_in_workflows() -> None:
    blob = CI.read_text(encoding="utf-8") + "\n" + DEPLOY.read_text(encoding="utf-8")
    # WHY: 평문 키·JSON private_key 금지 — ${{ secrets.* }} 만
    assert "BEGIN PRIVATE KEY" not in blob
    assert "AIza" not in blob
    assert "peaceful-basis" in blob  # 공개 프로젝트 id 는 OK


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
