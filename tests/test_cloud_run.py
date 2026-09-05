"""Cloud Run 문지기 계약 (0.2.24)."""

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
    # design/86 — deploy may use gcloud "${DEPLOY_ARGS[@]}" with "run deploy" parts.
    assert "gcloud run deploy" in script or (
        'gcloud "${DEPLOY_ARGS[@]}"' in script and "run deploy" in script
    )
    assert "ASR_COOKIE_SECURE" in script
    assert "--env-vars-file" in script
    assert "--remove-secrets=ASR_SMTP_USER,ASR_SMTP_PASS" in script
    assert "ASR_CD_SKIP_API_ENABLE" in (
        ROOT / ".github" / "workflows" / "deploy-cloud-run.yml"
    ).read_text(encoding="utf-8")
    assert "skip gcloud services enable" in script
    assert "--source" in script
    assert "ASR_KAKAO_REST_API_KEY" in script
    design = (ROOT / "docs" / "design" / "26-cloud-run-oauth-origin.md").read_text(
        encoding="utf-8"
    )
    assert "JavaScript" in design
    assert "0.2.23" in design
    assert "ASR_CLOUD_RUN_URL" in script
    assert "ASR_ADMIN_EMAILS" in script


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
    assert st["version"] == "0.3.156"


def test_index_asset_cache_bust() -> None:
    from fastapi.testclient import TestClient

    from sentence_reading.api.app import app

    html = TestClient(app).get("/").text
    assert "app.js?v=0.3.156" in html
    assert "styles.css?v=0.3.156" in html
    assert "__ASR_ASSET_V__" not in html


def test_cloud_url_in_auth_status(monkeypatch):
    monkeypatch.setenv("ASR_SKIP_ENV_FILE", "1")
    monkeypatch.setenv(
        "ASR_CLOUD_RUN_URL",
        "https://asr-sentence-reading-984608876300.asia-northeast3.run.app",
    )
    from fastapi.testclient import TestClient
    from sentence_reading.api.app import app
    from sentence_reading.llm import auth_google as ag
    # reload fields pick env
    st = TestClient(app).get("/api/status").json()
    assert st["auth"]["cloud_url"].startswith("https://asr-sentence-reading")
    assert "cloudUrlLink" in (
        Path(__file__).resolve().parents[1]
        / "src/sentence_reading/static/index.html"
    ).read_text(encoding="utf-8")


def test_gcs_ready_via_cloud_run_adc(monkeypatch: pytest.MonkeyPatch) -> None:
    from sentence_reading.llm import gcs_sync as gcs

    monkeypatch.setenv("ASR_GCS_BUCKET", "b")
    monkeypatch.delenv("GOOGLE_APPLICATION_CREDENTIALS", raising=False)
    monkeypatch.setenv("K_SERVICE", "asr-sentence-reading")
    ready, msg = gcs.gcs_client_ready()
    assert ready is True
    assert msg == "adc"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
