"""Flutter android/ platform contract (0.2.56 ship · app version tracks current)."""

from __future__ import annotations

import re
from pathlib import Path

from fastapi.testclient import TestClient

from sentence_reading.api.app import app

ROOT = Path(__file__).resolve().parents[1]
MOBILE = ROOT / "mobile"
ANDROID = MOBILE / "android"


def test_status_android_platform_flag() -> None:
    with TestClient(app) as client:
        st = client.get("/api/status").json()
    assert st["version"] == "0.3.56"
    assert st["mobile_flutter_scaffold"] is True
    assert st["mobile_android_platform"] is True
    assert "live_enable" not in st
    assert "ips" not in st


def test_android_tree_application_id_and_label() -> None:
    assert ANDROID.is_dir()
    gradle = (ANDROID / "app" / "build.gradle.kts").read_text(encoding="utf-8")
    assert 'applicationId = "com.gjtuc.sentence_reading"' in gradle
    assert 'namespace = "com.gjtuc.sentence_reading"' in gradle

    manifest = (ANDROID / "app" / "src" / "main" / "AndroidManifest.xml").read_text(
        encoding="utf-8"
    )
    assert 'android:label="문장 읽기"' in manifest
    assert "android.permission.INTERNET" in manifest

    activity = (
        ANDROID
        / "app"
        / "src"
        / "main"
        / "kotlin"
        / "com"
        / "gjtuc"
        / "sentence_reading"
        / "MainActivity.kt"
    )
    assert activity.is_file()
    body = activity.read_text(encoding="utf-8")
    assert "package com.gjtuc.sentence_reading" in body
    assert "FlutterActivity" in body
    assert "Trading Gate" in body or "Live Enable" in body


def test_local_properties_not_committed() -> None:
    """Edge: machine-local SDK path must stay gitignored."""
    gi = (MOBILE / ".gitignore").read_text(encoding="utf-8")
    assert "android/local.properties" in gi
    # Working tree may have the file; it must never be tracked.
    # (git check-ignore is optional; presence in gitignore is the contract.)


def test_no_secrets_in_android_sources() -> None:
    banned = re.compile(
        r"(AIza[0-9A-Za-z_-]{20,}|BEGIN (RSA |EC )?PRIVATE KEY|"
        r"GEMINI_API_KEY|client_secret|private_key)",
        re.I,
    )
    roots = [
        ANDROID / "app" / "src",
        ANDROID / "app" / "build.gradle.kts",
        ANDROID / "build.gradle.kts",
        ANDROID / "settings.gradle.kts",
    ]
    files: list[Path] = []
    for r in roots:
        if r.is_file():
            files.append(r)
        elif r.is_dir():
            files.extend(r.rglob("*"))
    assert files
    for path in files:
        if not path.is_file():
            continue
        if path.suffix.lower() in {".png", ".webp", ".jar", ".keystore", ".jks"}:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        assert banned.search(text) is None, f"secret-like pattern in {path}"


def test_design_48_and_readme() -> None:
    d48 = (ROOT / "docs/design/48-flutter-android-platform.md").read_text(encoding="utf-8")
    assert "0.2.56" in d48
    assert "mobile_android_platform" in d48
    assert "Trading Gate" in d48 or "ASR 밖" in d48
    # WHY: sideload pin closes the “phone lagging API” gap (historical Device E2E at 0.2.86).
    assert "Device E2E" in d48
    assert "versionName=0.2.86" in d48
    assert "[x] 실기 사이드로드 APK" in d48
    readme = (MOBILE / "README.md").read_text(encoding="utf-8")
    assert "android/" in readme.lower() or "Android" in readme
    assert "0.3.3" in readme
    assert "sideload" in readme.lower() or "사이드로드" in readme


def test_html_asset_bust_tracks_app_version() -> None:
    with TestClient(app) as client:
        html = client.get("/").text
    assert "app.js?v=0.3.56" in html
