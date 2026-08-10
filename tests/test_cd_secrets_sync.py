"""CD secrets sync / deploy SA 스크립트 계약 (0.2.96)."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
ENSURE = ROOT / "scripts" / "ensure_github_deploy_sa.sh"
SYNC = ROOT / "scripts" / "sync_github_cd_secrets.sh"


def _git_bash() -> str:
    env = (os.environ.get("GIT_BASH") or "").strip()
    for c in (
        env,
        r"C:\Program Files\Git\bin\bash.exe",
        r"C:\Program Files (x86)\Git\bin\bash.exe",
        "bash",
    ):
        if c and (c == "bash" or Path(c).is_file()):
            return c
    return "bash"


def _run(script: Path, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    merged = {**os.environ, **env}
    return subprocess.run(
        [_git_bash(), str(script)],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
        env=merged,
    )


def test_ensure_sa_dry_run() -> None:
    r = _run(ENSURE, {"ASR_CD_DRY_RUN": "1"})
    assert r.returncode == 0, (r.stdout, r.stderr)
    assert "dry-run:" in r.stdout
    assert "asr-github-deploy@" in r.stdout


def test_sync_dry_run_requires_sa_json(tmp_path: Path) -> None:
    # edge: SA JSON 없으면 exit 2 (env 는 있어도)
    env_file = tmp_path / "asr.env"
    env_file.write_text(
        "\n".join(
            [
                "ASR_GOOGLE_CLIENT_ID=cid",
                "ASR_AUTH_SECRET=sec",
                "GEMINI_API_KEY=key",
                "ASR_KAKAO_REST_API_KEY=r" * 8,
                "ASR_KAKAO_CLIENT_SECRET=s" * 8,
                "",
            ]
        ),
        encoding="utf-8",
    )
    missing = tmp_path / "no-such.json"
    r = _run(
        SYNC,
        {
            "ASR_CD_DRY_RUN": "1",
            "ASR_ENV_FILE": str(env_file),
            "ASR_CD_SA_JSON": str(missing),
        },
    )
    assert r.returncode == 2, (r.returncode, r.stdout, r.stderr)
    assert "missing SA_JSON" in (r.stdout + r.stderr)


def test_sync_dry_run_missing_env_file(tmp_path: Path) -> None:
    # edge: env 파일 없음 → exit 1
    r = _run(
        SYNC,
        {
            "ASR_CD_DRY_RUN": "1",
            "ASR_ENV_FILE": str(tmp_path / "gone.env"),
            "ASR_CD_SA_JSON": str(tmp_path / "x.json"),
        },
    )
    assert r.returncode == 1
    assert "missing env file" in (r.stdout + r.stderr)


def test_sync_dry_run_ok_with_sa_json() -> None:
    sa = Path(r"C:/Users/user/Desktop/.cursor/secrets/asr-github-deploy.json")
    if not sa.is_file():
        pytest.skip("deploy SA json not on this machine")
    r = _run(
        SYNC,
        {
            "ASR_CD_DRY_RUN": "1",
            "ASR_ENV_FILE": str(Path(r"C:/Users/user/Desktop/.cursor/gc_automation.env")),
            "ASR_CD_SA_JSON": str(sa),
        },
    )
    assert r.returncode == 0, (r.stdout, r.stderr)
    assert "dry-run: would set secrets" in r.stdout
    assert "ASR_GOOGLE_CLIENT_ID" in r.stdout


def test_design_and_status_version() -> None:
    design = (ROOT / "docs" / "design" / "32-github-cd.md").read_text(encoding="utf-8")
    assert "0.2.96" in design
    assert "sync_github_cd_secrets" in design
    assert "ensure_github_deploy_sa" in design
    from fastapi.testclient import TestClient

    from sentence_reading.api.app import app

    st = TestClient(app).get("/api/status").json()
    assert st["version"] == "0.2.96"
    assert st.get("github_cd") is True


def test_deploy_script_no_hardcoded_admin_email() -> None:
    """Security: deploy_cloud_run.sh must not bake a real admin email default."""
    text = (Path(__file__).resolve().parents[1] / "scripts" / "deploy_cloud_run.sh").read_text(
        encoding="utf-8"
    )
    assert "ASR_ADMIN_EMAILS:-}" in text or 'ASR_ADMIN_EMAILS:-"' in text or "${ASR_ADMIN_EMAILS:-}" in text
    assert "@gmail.com" not in text
    assert "configured_count" in text

