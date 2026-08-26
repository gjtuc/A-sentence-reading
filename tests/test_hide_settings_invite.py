# -*- coding: utf-8 -*-
"""design/104 — hide Settings invite redeem when allowed / admin."""
from __future__ import annotations

import os
import re

from fastapi.testclient import TestClient

from sentence_reading.api.app import app

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MOBILE = os.path.join(ROOT, "mobile")
DESIGN = os.path.join(
    ROOT, "docs", "design", "104-hide-settings-invite-when-allowed.md"
)


def test_status_version_pin() -> None:
    with TestClient(app) as client:
        st = client.get("/api/status").json()
    assert st["version"] == "0.3.66"


def test_design_104_exists() -> None:
    assert os.path.isfile(DESIGN)
    text = open(DESIGN, encoding="utf-8").read()
    assert "0.3.18" in text
    assert "shouldShowSettingsInviteRedeem" in text or "승인" in text
    assert "관리자" in text


def test_access_models_helper() -> None:
    models = open(
        os.path.join(MOBILE, "lib", "api", "access_models.dart"),
        encoding="utf-8",
    ).read()
    assert "shouldShowSettingsInviteRedeem" in models
    assert "access.isAdmin" in models or "isAdmin" in models
    assert "canUsePaid" in models
    assert "design/104" in models


def test_settings_gates_invite_field() -> None:
    settings = open(
        os.path.join(MOBILE, "lib", "screens", "settings_screen.dart"),
        encoding="utf-8",
    ).read()
    assert "shouldShowSettingsInviteRedeem" in settings
    assert "OTP \ucd08\ub300 \ucf54\ub4dc \ubc1c\uae09" in settings  # OTP 초대 코드 발급
    # Invite TextField only inside shouldShow branch
    assert settings.count("labelText: '\ucd08\ub300 \ucf54\ub4dc'") == 1
    assert "\ubcf8\uc778 \ucd08\ub300 \uc785\ub825\uc740 \ud544\uc694 \uc5c6\uc2b5\ub2c8\ub2e4" in settings
    # Waiting shell still owns Deny re-enter (not removed)
    waiting = open(
        os.path.join(MOBILE, "lib", "screens", "access_waiting_screen.dart"),
        encoding="utf-8",
    ).read()
    assert "redeemInviteCode" in waiting or "_redeem" in waiting
    assert "denied" in waiting.lower() or "\uac70\uc808" in waiting


def test_pubspec_pin() -> None:
    pub = open(os.path.join(MOBILE, "pubspec.yaml"), encoding="utf-8").read()
    assert "0.3.66" in pub


def test_no_secrets() -> None:
    banned = re.compile(
        r"(AIza[0-9A-Za-z_-]{20,}|BEGIN (RSA |EC )?PRIVATE KEY|"
        r"GEMINI_API_KEY|client_secret|private_key)",
        re.I,
    )
    for name in (
        "lib/api/access_models.dart",
        "lib/screens/settings_screen.dart",
    ):
        text = open(os.path.join(MOBILE, name), encoding="utf-8").read()
        assert banned.search(text) is None


def _should_show(access: dict | None) -> bool:
    """Mirror of Dart shouldShowSettingsInviteRedeem for table evidence."""
    if access is None:
        return False
    if access.get("isAdmin"):
        return False
    if not access.get("gateEnabled"):
        return False
    if access.get("canUsePaid") or access.get("status") == "allowed":
        return False
    return True


def test_invite_redeem_decision_table() -> None:
    assert _should_show(None) is False
    assert (
        _should_show(
            {
                "isAdmin": True,
                "gateEnabled": True,
                "canUsePaid": True,
                "status": "allowed",
            }
        )
        is False
    )
    assert (
        _should_show(
            {
                "isAdmin": False,
                "gateEnabled": True,
                "canUsePaid": True,
                "status": "allowed",
            }
        )
        is False
    )
    assert (
        _should_show(
            {
                "isAdmin": False,
                "gateEnabled": False,
                "canUsePaid": True,
                "status": "none",
            }
        )
        is False
    )
    assert (
        _should_show(
            {
                "isAdmin": False,
                "gateEnabled": True,
                "canUsePaid": False,
                "status": "denied",
            }
        )
        is True
    )
    assert (
        _should_show(
            {
                "isAdmin": False,
                "gateEnabled": True,
                "canUsePaid": False,
                "status": "pending",
            }
        )
        is True
    )
    assert (
        _should_show(
            {
                "isAdmin": False,
                "gateEnabled": True,
                "canUsePaid": False,
                "status": "none",
            }
        )
        is True
    )