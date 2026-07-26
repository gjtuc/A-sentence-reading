"""테스트 공통: 이메일 기본 on 이 레거시 GCS 경로 계약을 깨지 않도록 off."""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _default_email_auth_off(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ASR_EMAIL_AUTH", "0")
