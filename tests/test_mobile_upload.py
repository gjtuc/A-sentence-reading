"""Mobile single-PDF upload contract (0.3.3 · design/70)."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from sentence_reading.api.app import app

ROOT = Path(__file__).resolve().parents[1]
MOBILE = ROOT / "mobile"
DESIGN = ROOT / "docs" / "design" / "70-mobile-upload.md"


def test_status_mobile_upload_flag() -> None:
    with TestClient(app) as client:
        st = client.get("/api/status").json()
    assert st["version"] == "0.3.61"
    assert st["mobile_upload"] is True
    assert st["mobile_upload_resume"] is True
    assert st["ingest_job_gcs"] is True
    assert st["mobile_library"] is True
    assert "live_enable" not in st
    assert "ips" not in st


def test_design_70_and_pubspec() -> None:
    text = DESIGN.read_text(encoding="utf-8")
    assert "0.3.3" in text
    assert "Trading Gate" in text or "ASR 밖" in text
    assert "이어올리기" in text or "재개" in text
    assert "file_picker" in text
    pub = (MOBILE / "pubspec.yaml").read_text(encoding="utf-8")
    assert "0.3.61" in pub
    assert "file_picker:" in pub
    assert "path_provider:" in pub
    client = (MOBILE / "lib" / "api" / "client.dart").read_text(encoding="utf-8")
    assert "ingestPdfBytes" in client
    assert "pollIngestJob" in client
    assert "startIngestPdfBytes" in client
    lib = (MOBILE / "lib" / "screens" / "library_screen.dart").read_text(
        encoding="utf-8"
    )
    assert "PDF 가져오기" in lib
    assert "자동" in lib
    assert "resumePendingIfAny" in (
        MOBILE / "lib" / "state" / "library_controller.dart"
    ).read_text(encoding="utf-8")
    assert "앱 업로드는 후속" not in lib
    assert (ROOT / "docs" / "design" / "71-mobile-upload-resume.md").is_file()


def test_html_asset_bust_tracks_app_version() -> None:
    with TestClient(app) as client:
        html = client.get("/").text
    assert "app.js?v=0.3.61" in html


def test_unauth_cache_papers_empty_when_auth_on(monkeypatch) -> None:
    """Fail-closed: no session must not dump instance-local papers."""
    from sentence_reading.llm import papers_gcs

    monkeypatch.setattr(
        "sentence_reading.llm.auth_google.auth_enabled", lambda: True
    )
    monkeypatch.setattr(
        "sentence_reading.llm.auth_google.current_gcs_uid", lambda: None
    )
    assert papers_gcs.list_merged_paper_entries() == []
