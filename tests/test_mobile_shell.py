"""Mobile shell nav — auth gate · 3 tabs (0.3.3 · design/68)."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
MOBILE = ROOT / "mobile"
DESIGN = ROOT / "docs" / "design" / "68-mobile-shell-nav.md"


@pytest.fixture()
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("ASR_ACCESS_GATE", "0")
    from sentence_reading.api.app import app

    return TestClient(app)


def test_status_mobile_shell_nav(client: TestClient) -> None:
    st = client.get("/api/status").json()
    assert st["version"] == "0.3.35"
    assert st["mobile_shell_nav"] is True


def test_shell_source_structure() -> None:
    shell = (MOBILE / "lib" / "screens" / "home_shell.dart").read_text(encoding="utf-8")
    assert "isLoggedIn" in shell
    assert "LoginScreen" in shell
    assert "label: '보관'" in shell
    assert "label: '읽기'" in shell
    assert "label: '설정'" in shell
    # WHY: server/login are not bottom-nav destinations after 0.3.3.
    assert "label: '서버'" not in shell
    assert "label: '로그인'" not in shell
    settings = (MOBILE / "lib" / "screens" / "settings_screen.dart").read_text(
        encoding="utf-8"
    )
    assert "계정" in settings
    assert "로그아웃" in settings
    assert "StatusScreen" in settings
    assert "isAdmin" in settings
    login = (MOBILE / "lib" / "screens" / "login_screen.dart").read_text(encoding="utf-8")
    assert "Live Enable" not in login
    assert "Cloud Run" not in login
    assert "Trading Gate" not in login
    assert DESIGN.is_file()
    design = DESIGN.read_text(encoding="utf-8")
    assert "0.3.3" in design
    assert "mobile_shell_nav" in design or "Shell" in design
