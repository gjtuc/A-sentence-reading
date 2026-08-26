"""GitHub CI/CD 계약 (0.3.3 · design/32)."""

from __future__ import annotations

import importlib.util
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
CHECK = ROOT / "scripts" / "check_github_cd_ready.py"


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
    # WHY: 부모 셸에 카카오 키가 있어도 테스트 격리를 위해 명시적으로 비움
    for k in ("ASR_KAKAO_REST_API_KEY", "ASR_KAKAO_CLIENT_SECRET"):
        merged.setdefault(k, env.get(k, ""))
    if "ASR_KAKAO_REST_API_KEY" not in env:
        merged["ASR_KAKAO_REST_API_KEY"] = ""
    if "ASR_KAKAO_CLIENT_SECRET" not in env:
        merged["ASR_KAKAO_CLIENT_SECRET"] = ""
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
    deploy_text = DEPLOY.read_text(encoding="utf-8")
    deploy = yaml.safe_load(deploy_text)
    assert deploy["name"] == "Deploy Cloud Run"
    assert "ASR_CD_ENABLED" in str(deploy["jobs"]["deploy"].get("if", ""))
    assert "google-github-actions/auth@v2" in deploy_text
    assert "ASR_KAKAO_REST_API_KEY" in deploy_text
    assert "ASR_KAKAO_CLIENT_SECRET" in deploy_text
    assert "ASR_CD_SKIP_API_ENABLE" in deploy_text
    assert "ASR_SHADOWING_PRACTICE" in deploy_text
    assert "ASR_SHADOWING_PRACTICE" in SCRIPT.read_text(encoding="utf-8")
    design = DESIGN.read_text(encoding="utf-8")
    assert "0.3.3" in design
    assert "env-vars-file" in design or "env-vars-file" in SCRIPT.read_text(encoding="utf-8")
    assert "--env-vars-file" in SCRIPT.read_text(encoding="utf-8")


def test_deploy_dry_run_ok() -> None:
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
    assert "kakao=off" in r.stdout


def test_deploy_dry_run_kakao_on() -> None:
    r = _run_deploy(
        {
            "ASR_CD_DRY_RUN": "1",
            "ASR_GOOGLE_CLIENT_ID": "cid",
            "ASR_AUTH_SECRET": "sec",
            "GEMINI_API_KEY": "key",
            "ASR_KAKAO_REST_API_KEY": "a" * 32,
            "ASR_KAKAO_CLIENT_SECRET": "b" * 32,
        }
    )
    assert r.returncode == 0, (r.stdout, r.stderr)
    assert "kakao=on" in r.stdout


def test_deploy_dry_run_kakao_partial_fails() -> None:
    # edge: REST 만 있으면 wipe/불완전 — 거부
    r = _run_deploy(
        {
            "ASR_CD_DRY_RUN": "1",
            "ASR_GOOGLE_CLIENT_ID": "cid",
            "ASR_AUTH_SECRET": "sec",
            "GEMINI_API_KEY": "key",
            "ASR_KAKAO_REST_API_KEY": "only-rest",
            "ASR_KAKAO_CLIENT_SECRET": "",
        }
    )
    assert r.returncode == 2
    assert "partial" in (r.stdout + r.stderr)


def test_deploy_missing_env_fails() -> None:
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


def test_status_github_cd_flag() -> None:
    from fastapi.testclient import TestClient

    from sentence_reading.api.app import app

    st = TestClient(app).get("/api/status").json()
    assert st["version"] == "0.3.58"
    assert st.get("github_cd") is True


def test_no_secrets_in_workflows() -> None:
    blob = CI.read_text(encoding="utf-8") + "\n" + DEPLOY.read_text(encoding="utf-8")
    assert "BEGIN PRIVATE KEY" not in blob
    assert "AIza" not in blob
    assert "peaceful-basis" in blob


def test_check_github_cd_ready_evaluate() -> None:
    spec = importlib.util.spec_from_file_location("check_github_cd_ready", CHECK)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    empty = mod.evaluate(secret_names=set(), variables={})
    assert empty["ok"] is False
    assert "GCP_SA_KEY" in empty["missing_required_secrets"]
    full = mod.evaluate(
        secret_names=set(mod.REQUIRED_SECRETS)
        | {"ASR_KAKAO_REST_API_KEY", "ASR_KAKAO_CLIENT_SECRET"},
        variables={"ASR_CD_ENABLED": "0"},
    )
    assert full["ok"] is True
    assert full["kakao"] == "on"
    assert full["can_enable"] is True
    partial = mod.evaluate(
        secret_names=set(mod.REQUIRED_SECRETS) | {"ASR_KAKAO_REST_API_KEY"},
        variables={},
    )
    assert partial["ok"] is False
    assert partial["kakao"] == "partial"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
