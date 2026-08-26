"""Live SMTP wiring contract (0.3.3 · design/86)."""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]


def _bash_exe() -> str:
    # WHY: Windows Python's PATH ``bash`` may be the WSL stub (UTF-16 noise, exit 1).
    if sys.platform == "win32":
        git_bash = Path(r"C:\Program Files\Git\bin\bash.exe")
        if git_bash.is_file():
            return str(git_bash)
    return "bash"


def test_status_exposes_smtp_bool_without_secrets(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ASR_SMTP_HOST", raising=False)
    monkeypatch.delenv("ASR_SMTP_FROM", raising=False)
    from sentence_reading.api.app import app

    st = TestClient(app).get("/api/status").json()
    assert st["version"] == "0.3.58"
    assert st.get("email_smtp_configured") is False
    # SECURITY: never leak connection details on status.
    blob = str(st)
    assert "ASR_SMTP_PASS" not in blob
    assert "smtp.gmail" not in blob.lower()


def test_status_smtp_true_when_host_and_from(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ASR_SMTP_HOST", "smtp.example.test")
    monkeypatch.setenv("ASR_SMTP_FROM", "noreply@example.test")
    monkeypatch.delenv("ASR_SMTP_PASS", raising=False)
    from sentence_reading.api.app import app

    st = TestClient(app).get("/api/status").json()
    assert st.get("email_smtp_configured") is True
    assert "noreply@example.test" not in str(st)


def test_deploy_script_secretmanager_fallback() -> None:
    """host+from without USER/PASS → Secret Manager attach path (no password in env file)."""
    deploy = (ROOT / "scripts" / "deploy_cloud_run.sh").read_text(encoding="utf-8")
    assert "secretmanager" in deploy
    assert "--set-secrets" in deploy
    assert "st-auth-smtp-user" in deploy
    assert "ASR_SMTP_PASS" in deploy
    # plain FORCE path still documents remove-secrets pre-step.
    assert "ASR_SMTP_FORCE_PLAIN" in deploy
    assert "--remove-secrets=ASR_SMTP_USER,ASR_SMTP_PASS" in deploy


def test_deploy_script_and_workflow_wire_smtp() -> None:
    deploy = (ROOT / "scripts" / "deploy_cloud_run.sh").read_text(encoding="utf-8")
    assert "ASR_SMTP_HOST" in deploy
    assert "ASR_SMTP_FROM" in deploy
    assert "ASR_SMTP_PASS" in deploy
    assert "design/86" in deploy
    wf = (ROOT / ".github" / "workflows" / "deploy-cloud-run.yml").read_text(
        encoding="utf-8"
    )
    assert "ASR_SMTP_HOST" in wf
    assert "secrets.ASR_SMTP_PASS" in wf
    sync = (ROOT / "scripts" / "sync_github_cd_secrets.sh").read_text(encoding="utf-8")
    assert "ASR_SMTP_HOST" in sync
    design = (ROOT / "docs" / "design" / "86-live-smtp-wiring.md").read_text(
        encoding="utf-8"
    )
    assert "0.3.3" in design
    assert "REDACTED" in design or "불필요" in design or "secret" in design.lower()


def test_deploy_dry_run_rejects_partial_smtp(monkeypatch: pytest.MonkeyPatch) -> None:
    import subprocess

    env = os.environ.copy()
    env["ASR_CD_DRY_RUN"] = "1"
    env["ASR_GOOGLE_CLIENT_ID"] = "x.apps.googleusercontent.com"
    env["ASR_AUTH_SECRET"] = "test-secret-not-real-32chars-ok"
    env["GEMINI_API_KEY"] = "test-gemini-not-real"
    env["ASR_SMTP_HOST"] = "smtp.example.test"
    env.pop("ASR_SMTP_FROM", None)
    r = subprocess.run(
        [_bash_exe(), str(ROOT / "scripts" / "deploy_cloud_run.sh")],
        cwd=ROOT,
        env=env,
        capture_output=True,
    )
    # WHY: keep bytes decode fail-closed on mixed Windows encodings.
    out = (r.stdout or b"").decode("utf-8", errors="replace")
    err = (r.stderr or b"").decode("utf-8", errors="replace")
    assert r.returncode == 2
    assert "ASR_SMTP_FROM" in (err + out)


def test_mail_copy_mentions_browser_or_app() -> None:
    text = (ROOT / "src" / "sentence_reading" / "llm" / "email_smtp.py").read_text(
        encoding="utf-8"
    )
    assert "브라우저 또는 앱" in text
    assert "앱으로 이동합니다" not in text
