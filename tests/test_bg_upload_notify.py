"""Background upload notification contract (0.3.3 · design/74)."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from sentence_reading.api.app import app

ROOT = Path(__file__).resolve().parents[1]
DESIGN = ROOT / "docs" / "design" / "74-bg-upload-notify.md"
MOBILE = ROOT / "mobile"


def test_status_mobile_upload_background_flag() -> None:
    with TestClient(app) as client:
        st = client.get("/api/status").json()
    assert st["version"] == "0.3.32"
    assert st["mobile_upload_background"] is True
    assert st["mobile_upload"] is True
    assert st["ingest_chunked_upload"] is True
    # WHY: Trading Live Enable / IPS are out of this product surface.
    assert "live_enable" not in st
    assert "ips" not in st


def test_kill_switch_disables_background_flag(monkeypatch) -> None:
    monkeypatch.setenv("ASR_MOBILE_UPLOAD_BACKGROUND", "0")
    with TestClient(app) as client:
        st = client.get("/api/status").json()
    assert st["mobile_upload_background"] is False


def test_design_74_and_android_wiring() -> None:
    text = DESIGN.read_text(encoding="utf-8")
    assert "0.3.3" in text
    assert "ASR_MOBILE_UPLOAD_BACKGROUND" in text
    assert "mobile_upload_background" in text
    assert "Live Enable" in text or "IPS" in text

    pub = (MOBILE / "pubspec.yaml").read_text(encoding="utf-8")
    assert "0.3.32" in pub

    notify = (MOBILE / "lib" / "api" / "upload_notify.dart").read_text(
        encoding="utf-8"
    )
    assert "asr/upload_notify" in notify
    assert "sanitizeNotifyStage" in notify

    lib = (MOBILE / "lib" / "state" / "library_controller.dart").read_text(
        encoding="utf-8"
    )
    assert "_maybeStartNotify" in lib
    assert "openByCacheId" in lib

    manifest = (
        MOBILE
        / "android"
        / "app"
        / "src"
        / "main"
        / "AndroidManifest.xml"
    ).read_text(encoding="utf-8")
    assert "FOREGROUND_SERVICE_DATA_SYNC" in manifest
    assert "UploadForegroundService" in manifest
    assert "SystemForegroundService" in manifest
    assert "stopWithTask" in manifest
    assert "WAKE_LOCK" in manifest

    svc = (
        MOBILE
        / "android"
        / "app"
        / "src"
        / "main"
        / "kotlin"
        / "com"
        / "gjtuc"
        / "sentence_reading"
        / "UploadForegroundService.kt"
    )
    assert svc.is_file()
    svc_body = svc.read_text(encoding="utf-8")
    assert "PARTIAL_WAKE_LOCK" in svc_body
    assert "asr:upload_fg" in svc_body
    main = (
        MOBILE
        / "android"
        / "app"
        / "src"
        / "main"
        / "kotlin"
        / "com"
        / "gjtuc"
        / "sentence_reading"
        / "MainActivity.kt"
    ).read_text(encoding="utf-8")
    assert "startUploadNotify" in main
    assert "takePendingOpenCacheId" in main


def test_html_asset_bust_tracks_app_version() -> None:
    with TestClient(app) as client:
        html = client.get("/").text
    assert "app.js?v=0.3.32" in html
