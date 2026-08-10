"""WorkManager upload resume contract (0.2.98 · design/76)."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from sentence_reading.api.app import app

ROOT = Path(__file__).resolve().parents[1]
DESIGN = ROOT / "docs" / "design" / "76-upload-workmanager.md"
MOBILE = ROOT / "mobile"
KT = (
    MOBILE
    / "android"
    / "app"
    / "src"
    / "main"
    / "kotlin"
    / "com"
    / "gjtuc"
    / "sentence_reading"
)


def test_status_mobile_upload_workmanager_flag() -> None:
    with TestClient(app) as client:
        st = client.get("/api/status").json()
    assert st["version"] == "0.2.98"
    assert st["mobile_upload_workmanager"] is True
    assert st["mobile_upload_interrupt_resume"] is True
    assert st["mobile_upload_background"] is True
    # WHY: Trading Live Enable / IPS are out of this product surface.
    assert "live_enable" not in st
    assert "ips" not in st


def test_kill_switch_disables_workmanager_flag(monkeypatch) -> None:
    monkeypatch.setenv("ASR_MOBILE_UPLOAD_WORKMANAGER", "0")
    with TestClient(app) as client:
        st = client.get("/api/status").json()
    assert st["mobile_upload_workmanager"] is False


def test_design_76_and_android_wiring() -> None:
    text = DESIGN.read_text(encoding="utf-8")
    assert "0.2.98" in text
    assert "ASR_MOBILE_UPLOAD_WORKMANAGER" in text
    assert "mobile_upload_workmanager" in text
    assert "WorkManager" in text
    assert "Live Enable" in text or "IPS" in text

    pub = (MOBILE / "pubspec.yaml").read_text(encoding="utf-8")
    assert "0.2.98" in pub

    gradle = (MOBILE / "android" / "app" / "build.gradle.kts").read_text(
        encoding="utf-8"
    )
    assert "work-runtime-ktx" in gradle
    assert "isMinifyEnabled = false" in gradle

    proguard = (MOBILE / "android" / "app" / "proguard-rules.pro").read_text(
        encoding="utf-8"
    )
    assert "androidx.work" in proguard
    assert "WorkDatabase" in proguard

    manifest = (
        MOBILE
        / "android"
        / "app"
        / "src"
        / "main"
        / "AndroidManifest.xml"
    ).read_text(encoding="utf-8")
    assert "SystemForegroundService" in manifest
    assert "dataSync" in manifest

    notify = (MOBILE / "lib" / "api" / "upload_notify.dart").read_text(
        encoding="utf-8"
    )
    assert "scheduleUploadResume" in notify
    assert "cancelUploadResume" in notify
    assert "openBatterySettings" in notify
    assert "kBatteryHintDismissedHashKey" in notify

    lib = (MOBILE / "lib" / "state" / "library_controller.dart").read_text(
        encoding="utf-8"
    )
    assert "_scheduleWorkmanager" in lib
    assert "uploadBatteryHint" in lib
    assert "dismissBatteryHint" in lib

    main = (KT / "MainActivity.kt").read_text(encoding="utf-8")
    assert "scheduleUploadResume" in main
    assert "cancelUploadResume" in main
    assert "openBatterySettings" in main

    worker = (KT / "UploadResumeWorker.kt").read_text(encoding="utf-8")
    assert "UploadResumeWorker" in worker
    assert "KEY_DRAFT" in worker
    assert "KEY_SESSION" in worker
    # INVARIANT: session must not be Work input — prefs + Cookie header only.
    assert "setInputData" not in worker
    assert "asr_session=" in worker

    sched = (KT / "UploadResumeScheduler.kt").read_text(encoding="utf-8")
    assert "asr_upload_resume_v1" in sched
    assert "ExistingWorkPolicy.REPLACE" in sched

    idx = (ROOT / "docs" / "design" / "README.md").read_text(encoding="utf-8")
    assert "76-upload-workmanager.md" in idx


def test_html_asset_bust_tracks_app_version() -> None:
    with TestClient(app) as client:
        html = client.get("/").text
    assert "app.js?v=0.2.98" in html
