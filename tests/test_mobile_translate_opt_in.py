# -*- coding: utf-8 -*-
"""design/99 - mobile translate opt-in (ingest/open query gate)."""
from __future__ import annotations

import os

from fastapi.testclient import TestClient

from sentence_reading.api import app as app_mod


def test_status_version_pin() -> None:
    with TestClient(app_mod.app) as client:
        st = client.get("/api/status").json()
    assert st["version"] == "0.3.29"


def test_want_translate_absent_defaults_on() -> None:
    """Web compat: no query -> translate work stays on."""
    from starlette.requests import Request

    scope = {
        "type": "http",
        "method": "GET",
        "path": "/",
        "headers": [],
        "query_string": b"",
    }
    req = Request(scope)
    assert app_mod._want_translate(req) is True


def test_want_translate_explicit_off() -> None:
    from starlette.requests import Request

    scope = {
        "type": "http",
        "method": "GET",
        "path": "/",
        "headers": [],
        "query_string": b"translate=0",
    }
    req = Request(scope)
    assert app_mod._want_translate(req) is False


def test_want_translate_explicit_on() -> None:
    from starlette.requests import Request

    scope = {
        "type": "http",
        "method": "GET",
        "path": "/",
        "headers": [],
        "query_string": b"translate=1",
    }
    req = Request(scope)
    assert app_mod._want_translate(req) is True


def test_mobile_settings_has_translate_switch() -> None:
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    settings = open(
        os.path.join(root, "mobile", "lib", "screens", "settings_screen.dart"),
        encoding="utf-8",
    ).read()
    models = open(
        os.path.join(root, "mobile", "lib", "api", "translate_models.dart"),
        encoding="utf-8",
    ).read()
    client = open(
        os.path.join(root, "mobile", "lib", "api", "client.dart"),
        encoding="utf-8",
    ).read()
    # "?? ??"
    assert "\ubc88\uc5ed \uc0ac\uc6a9" in settings
    assert "asr.translate.v1" in models
    assert "parseTranslateEnabledPref" in models
    assert "translate=0" in client
    assert "translate=1" in client
    pub = open(
        os.path.join(root, "mobile", "pubspec.yaml"), encoding="utf-8"
    ).read()
    assert "0.3.29" in pub
