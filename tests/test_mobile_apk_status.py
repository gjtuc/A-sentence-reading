# -*- coding: utf-8 -*-
"""design/161 — /api/status mobile_apk_url."""
from __future__ import annotations

from fastapi.testclient import TestClient

from sentence_reading.api.app import app


def test_mobile_apk_url_missing_by_default(monkeypatch) -> None:
    monkeypatch.delenv("ASR_MOBILE_APK_URL", raising=False)
    monkeypatch.setenv("ASR_SKIP_ENV_FILE", "1")
    st = TestClient(app).get("/api/status").json()
    assert st.get("mobile_apk_url") is None


def test_mobile_apk_url_from_env(monkeypatch) -> None:
    monkeypatch.setenv("ASR_SKIP_ENV_FILE", "1")
    monkeypatch.setenv(
        "ASR_MOBILE_APK_URL",
        "https://storage.googleapis.com/asr-chaheon-warehouse/asr/mobile/sentence-reading-latest.apk",
    )
    st = TestClient(app).get("/api/status").json()
    assert (
        st.get("mobile_apk_url")
        == "https://storage.googleapis.com/asr-chaheon-warehouse/asr/mobile/sentence-reading-latest.apk"
    )
