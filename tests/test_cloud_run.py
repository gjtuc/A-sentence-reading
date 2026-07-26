"""Cloud Run 문지기 계약 (0.2.21)."""

from __future__ import annotations

from pathlib import Path

import pytest

from sentence_reading.llm import auth_google as ag


ROOT = Path(__file__).resolve().parents[1]


def test_dockerfile_and_deploy_script_exist() -> None:
    docker = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    assert "uvicorn sentence_reading.api.app:app" in docker
    assert "${PORT}" in docker
    assert "GOOGLE_APPLICATION_CREDENTIALS" not in docker
    script = (ROOT / "scripts" / "deploy_cloud_run.sh").read_text(encoding="utf-8")
    assert "gcloud run deploy" in script
    assert "ASR_COOKIE_SECURE=1" in script
    assert "--source" in script
    design = (ROOT / "docs" / "design" / "25-cloud-run.md").read_text(encoding="utf-8")
    assert "Cloud Run" in design
    assert "0.2.21" in design


def test_cookie_secure_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ASR_SKIP_ENV_FILE", "1")
    monkeypatch.delenv("ASR_COOKIE_SECURE", raising=False)
    assert ag.cookie_secure() is False
    monkeypatch.setenv("ASR_COOKIE_SECURE", "1")
    assert ag.cookie_secure() is True


def test_status_version() -> None:
    from fastapi.testclient import TestClient

    from sentence_reading.api.app import app

    st = TestClient(app).get("/api/status").json()
    assert st["version"] == "0.2.21"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
