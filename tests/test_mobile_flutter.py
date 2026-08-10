"""Flutter mobile/ scaffold contract (0.2.93 · design/33 · design/47)."""

from __future__ import annotations

import re
from pathlib import Path

from fastapi.testclient import TestClient

from sentence_reading.api.app import app

ROOT = Path(__file__).resolve().parents[1]
MOBILE = ROOT / "mobile"


def test_status_exposes_mobile_scaffold_flag() -> None:
    with TestClient(app) as client:
        st = client.get("/api/status").json()
    assert st["version"] == "0.2.93"
    assert st["mobile_flutter_scaffold"] is True
    # Live Enable / IPS belong to Trading Gate — never on ASR status
    assert "live_enable" not in st
    assert "ips" not in st


def test_mobile_tree_and_pubspec() -> None:
    assert MOBILE.is_dir()
    pub = (MOBILE / "pubspec.yaml").read_text(encoding="utf-8")
    assert "name: sentence_reading" in pub
    assert "0.2.93" in pub or "0.2.56" in pub
    assert "http:" in pub
    assert (MOBILE / "lib" / "main.dart").is_file()
    assert (MOBILE / "lib" / "config.dart").is_file()
    assert (MOBILE / "lib" / "api" / "client.dart").is_file()
    for name in ("login_screen.dart", "library_screen.dart", "reader_screen.dart", "status_screen.dart"):
        assert (MOBILE / "lib" / "screens" / name).is_file()
    readme = (MOBILE / "README.md").read_text(encoding="utf-8")
    assert "com.gjtuc.sentence_reading" in readme
    assert "문장 읽기" in readme


def test_no_secrets_in_mobile_dart() -> None:
    """Edge / security: client must not embed Gemini/GCS/private keys."""
    banned = re.compile(
        r"(AIza[0-9A-Za-z_-]{20,}|BEGIN (RSA |EC )?PRIVATE KEY|"
        r"GEMINI_API_KEY|GOOGLE_APPLICATION_CREDENTIALS|"
        r"client_secret|private_key)",
        re.I,
    )
    dart_files = list(MOBILE.rglob("*.dart"))
    assert dart_files, "expected dart sources"
    for path in dart_files:
        text = path.read_text(encoding="utf-8")
        assert banned.search(text) is None, f"secret-like pattern in {path}"


def test_config_points_at_known_cloud_run() -> None:
    cfg = (MOBILE / "lib" / "config.dart").read_text(encoding="utf-8")
    assert "asr-sentence-reading-984608876300.asia-northeast3.run.app" in cfg
    assert "throw ArgumentError" in cfg  # empty base URL rejected
    client = (MOBILE / "lib" / "api" / "client.dart").read_text(encoding="utf-8")
    assert "/api/status" in client
    assert "/api/auth/email/login" in client
    assert "AsrApiException" in client


def test_design_notes_scaffold_shipped() -> None:
    d33 = (ROOT / "docs/design/33-mobile-flutter.md").read_text(encoding="utf-8")
    d47 = (ROOT / "docs/design/47-flutter-scaffold.md").read_text(encoding="utf-8")
    assert "0.2.55" in d47 or "mobile_flutter_scaffold" in d47
    assert "0.2.56" in d33 or "mobile_android_platform" in d33
    assert "Live Enable" in d47
    assert "Trading Gate" in d47 or "ASR 밖" in d47
    assert "mobile_flutter_scaffold" in d47


def test_html_asset_bust_tracks_app_version() -> None:
    with TestClient(app) as client:
        html = client.get("/").text
    assert "app.js?v=0.2.93" in html
    assert "styles.css?v=0.2.93" in html
