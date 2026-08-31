# -*- coding: utf-8 -*-
"""design/161 — /api/status mobile_apk_url and /api/mobile/apk proxy."""
from __future__ import annotations

from fastapi.testclient import TestClient

from sentence_reading.api.app import app


def test_mobile_apk_url_defaults_to_request_base(monkeypatch) -> None:
    monkeypatch.delenv("ASR_MOBILE_APK_URL", raising=False)
    monkeypatch.delenv("ASR_CLOUD_RUN_URL", raising=False)
    monkeypatch.setenv("ASR_SKIP_ENV_FILE", "1")
    st = TestClient(app).get("/api/status").json()
    assert st.get("mobile_apk_url") == "http://testserver/api/mobile/apk"


def test_mobile_apk_url_from_env(monkeypatch) -> None:
    monkeypatch.setenv("ASR_SKIP_ENV_FILE", "1")
    monkeypatch.setenv(
        "ASR_MOBILE_APK_URL",
        "https://example.com/custom.apk",
    )
    st = TestClient(app).get("/api/status").json()
    assert st.get("mobile_apk_url") == "https://example.com/custom.apk"


def test_mobile_apk_url_defaults_to_cloud_run_proxy(monkeypatch) -> None:
    monkeypatch.setenv("ASR_SKIP_ENV_FILE", "1")
    monkeypatch.delenv("ASR_MOBILE_APK_URL", raising=False)
    monkeypatch.setenv(
        "ASR_CLOUD_RUN_URL",
        "https://asr-sentence-reading-984608876300.asia-northeast3.run.app",
    )
    st = TestClient(app).get("/api/status").json()
    assert (
        st.get("mobile_apk_url")
        == "https://asr-sentence-reading-984608876300.asia-northeast3.run.app/api/mobile/apk"
    )


def test_mobile_apk_path_is_login_public() -> None:
    from sentence_reading.llm.login_required import is_login_public_path

    assert is_login_public_path("/api/mobile/apk")


def test_mobile_apk_download_serves_bytes(monkeypatch) -> None:
    monkeypatch.setenv("ASR_SKIP_ENV_FILE", "1")
    payload = b"PK\x03\x04fake-apk"

    def _ready() -> tuple[bool, str]:
        return True, "ok"

    monkeypatch.setattr(
        "sentence_reading.api.app.mobile_apk_ready",
        _ready,
    )
    monkeypatch.setattr(
        "sentence_reading.api.app.iter_mobile_apk_chunks",
        lambda **_: iter([payload]),
    )
    r = TestClient(app).get("/api/mobile/apk")
    assert r.status_code == 200
    assert r.content == payload
    assert "android.package-archive" in r.headers["content-type"]


def test_mobile_apk_download_not_found(monkeypatch) -> None:
    monkeypatch.setenv("ASR_SKIP_ENV_FILE", "1")

    def _ready() -> tuple[bool, str]:
        return True, "ok"

    monkeypatch.setattr("sentence_reading.api.app.mobile_apk_ready", _ready)
    monkeypatch.setattr(
        "sentence_reading.api.app.iter_mobile_apk_chunks",
        lambda **_: None,
    )
    r = TestClient(app).get("/api/mobile/apk")
    assert r.status_code == 404
    assert r.json()["error"] == "apk_not_found"
