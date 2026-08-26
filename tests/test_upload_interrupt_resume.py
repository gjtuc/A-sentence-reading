"""Upload interrupt auto-resume contract (0.3.3 · design/75)."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from sentence_reading.api.app import app

ROOT = Path(__file__).resolve().parents[1]
DESIGN = ROOT / "docs" / "design" / "75-upload-interrupt-resume.md"
MOBILE = ROOT / "mobile"


def test_status_interrupt_resume_flag() -> None:
    with TestClient(app) as client:
        st = client.get("/api/status").json()
    assert st["version"] == "0.3.60"
    assert st["mobile_upload_interrupt_resume"] is True
    assert st["mobile_upload_background"] is True
    assert "live_enable" not in st
    assert "ips" not in st


def test_kill_switch_disables_interrupt_flag(monkeypatch) -> None:
    monkeypatch.setenv("ASR_MOBILE_UPLOAD_INTERRUPT_RESUME", "0")
    with TestClient(app) as client:
        st = client.get("/api/status").json()
    assert st["mobile_upload_interrupt_resume"] is False


def test_design_75_and_client_wiring() -> None:
    text = DESIGN.read_text(encoding="utf-8")
    assert "0.3.3" in text
    assert "ASR_MOBILE_UPLOAD_INTERRUPT_RESUME" in text
    assert "approach A" in text.lower() or "Lifecycle" in text or "lifecycle" in text
    assert "45" in text

    pub = (MOBILE / "pubspec.yaml").read_text(encoding="utf-8")
    assert "0.3.60" in pub

    lib = (MOBILE / "lib" / "state" / "library_controller.dart").read_text(
        encoding="utf-8"
    )
    assert "onAppResumed" in lib
    assert "kUploadStallAfter" in lib
    assert "showInterrupted" in lib

    notify = (MOBILE / "lib" / "api" / "upload_notify.dart").read_text(
        encoding="utf-8"
    )
    assert "showInterrupted" in notify
    assert "업로드 중단됨" in notify

    shell = (MOBILE / "lib" / "screens" / "home_shell.dart").read_text(
        encoding="utf-8"
    )
    assert "onAppResumed" in shell


def test_html_asset_bust_tracks_app_version() -> None:
    with TestClient(app) as client:
        html = client.get("/").text
    assert "app.js?v=0.3.60" in html
