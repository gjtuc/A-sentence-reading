"""design/146c — Mobile Kakao OAuth scheme (flutter_web_auth_2 hyphen fix)."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from sentence_reading.llm.auth_google import (
    MOBILE_GOOGLE_DEEP_LINK,
    MOBILE_KAKAO_DEEP_LINK,
    MOBILE_MAGIC_DEEP_LINK,
    MOBILE_OAUTH_SCHEME,
    mobile_kakao_deep_link,
)

ROOT = Path(__file__).resolve().parents[1]
MOBILE = ROOT / "mobile"
MANIFEST = MOBILE / "android" / "app" / "src" / "main" / "AndroidManifest.xml"
OAUTH_MODELS = MOBILE / "lib" / "api" / "oauth_models.dart"

# flutter_web_auth_2 v4 — must match Dart _schemeRegExp.
_FLUTTER_WEB_AUTH_SCHEME_RE = re.compile(r"^[a-z][a-z\d+.-]*$")


def test_mobile_oauth_scheme_passes_flutter_web_auth_regex() -> None:
    assert _FLUTTER_WEB_AUTH_SCHEME_RE.fullmatch(MOBILE_OAUTH_SCHEME)
    assert "_" not in MOBILE_OAUTH_SCHEME


def test_mobile_deep_link_prefixes_use_hyphen_scheme() -> None:
    assert MOBILE_KAKAO_DEEP_LINK.startswith("com.gjtuc.sentence-reading://oauth/kakao")
    assert MOBILE_MAGIC_DEEP_LINK.startswith("com.gjtuc.sentence-reading://oauth/magic")
    assert MOBILE_GOOGLE_DEEP_LINK.startswith("com.gjtuc.sentence-reading://oauth/google")
    assert mobile_kakao_deep_link(session="tok", auth="logged_in").startswith(
        "com.gjtuc.sentence-reading://oauth/kakao?"
    )


def test_android_manifest_callback_activity_and_scheme() -> None:
    text = MANIFEST.read_text(encoding="utf-8")
    assert "com.linusu.flutter_web_auth_2.CallbackActivity" in text
    assert 'android:scheme="com.gjtuc.sentence-reading"' in text
    gradle = (MOBILE / "android" / "app" / "build.gradle.kts").read_text(encoding="utf-8")
    assert 'applicationId = "com.gjtuc.sentence_reading"' in gradle


def test_dart_oauth_scheme_matches_server() -> None:
    dart = OAUTH_MODELS.read_text(encoding="utf-8")
    assert "com.gjtuc.sentence-reading" in dart
    assert "kMobileOAuthScheme = 'com.gjtuc.sentence-reading'" in dart


def test_kakao_callback_mobile_deep_link_hyphen_scheme(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from fastapi.testclient import TestClient

    from sentence_reading.api.app import app
    from sentence_reading.llm.auth_google import issue_oauth_state

    def fake_exchange(code: str, *, redirect_uri: str) -> dict:
        return {
            "subject": "kakao-99",
            "email": "",
            "name": "K",
            "picture": "",
        }

    monkeypatch.setenv("ASR_KAKAO_REST_API_KEY", "kakao-rest-test")
    monkeypatch.setattr("sentence_reading.api.app.kakao_exchange_code", fake_exchange)
    state = issue_oauth_state("login", mobile=True)
    client = TestClient(app)
    r = client.get(
        "/api/auth/kakao/callback",
        params={"code": "abc", "state": state},
        follow_redirects=False,
    )
    assert r.status_code == 302
    loc = r.headers.get("location") or ""
    assert loc.startswith("com.gjtuc.sentence-reading://oauth/kakao?")
