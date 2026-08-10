"""테스트 공통: 실기기 env(gc_automation.env)가 계약을 깨지 않게 격리.

design/78 — production defaults ASR_EMAIL_PASSWORD off; enable it here so
fixtures that still register via email+password keep working. Tests that
assert the kill override with ASR_EMAIL_PASSWORD=0.
"""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _isolate_asr_env(monkeypatch: pytest.MonkeyPatch) -> None:
    # WHY: 운영 PC 의 gc_automation.env(버킷·OAuth)가 setdefault 로 테스트에 섞임
    monkeypatch.setenv("ASR_SKIP_ENV_FILE", "1")
    monkeypatch.setenv("ASR_EMAIL_AUTH", "0")
    monkeypatch.setenv("ASR_EMAIL_PASSWORD", "1")
    monkeypatch.delenv("ASR_GOOGLE_CLIENT_ID", raising=False)
    monkeypatch.delenv("ASR_KAKAO_REST_API_KEY", raising=False)
    monkeypatch.delenv("ASR_GCS_BUCKET", raising=False)
