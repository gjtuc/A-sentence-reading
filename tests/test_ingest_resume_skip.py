# -*- coding: utf-8 -*-
"""design/112 — mid-stage ingest resume skip (payload consume)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from sentence_reading.api import app as app_mod
from sentence_reading.api.app import app
from sentence_reading.llm import auth_accounts as aa
from sentence_reading.llm import auth_google as agu
from sentence_reading.llm import ingest_jobs_gcs as ij
from sentence_reading.llm import ingest_resume_payload as irp
from sentence_reading.llm import vision_ocr as vo
from sentence_reading.llm.extract_quality import QualityDecision
from sentence_reading.llm.typography import PIPELINE_VERSION
from sentence_reading.models import Sentence

ROOT = Path(__file__).resolve().parents[1]
DESIGN = ROOT / "docs" / "design" / "112-ingest-resume-skip.md"
PUB = ROOT / "mobile" / "pubspec.yaml"


@pytest.fixture()
def fake_gcs(monkeypatch: pytest.MonkeyPatch):
    bucket: dict[str, bytes] = {}

    def upload(name: str, data: bytes, *, content_type: str = "", meter: bool = True) -> bool:
        bucket[name] = bytes(data)
        return True

    def download(name: str, *, meter: bool = True) -> bytes | None:
        return bucket.get(name)

    def delete(name: str) -> bool:
        return bucket.pop(name, None) is not None

    monkeypatch.setenv("ASR_GCS_BUCKET", "fake-bucket")
    monkeypatch.setenv("ASR_ACCESS_GATE", "0")
    monkeypatch.setenv("ASR_AUTH_SECRET", "resume-skip-secret")
    monkeypatch.setenv("ASR_EMAIL_AUTH", "1")
    monkeypatch.setenv("ASR_INGEST_JOB_RECLAIM", "1")
    monkeypatch.setenv("ASR_INGEST_CHECKPOINT", "1")
    monkeypatch.setenv("ASR_INGEST_RESUME_SKIP", "1")
    monkeypatch.setattr("sentence_reading.llm.gcs_sync.upload_bytes", upload)
    monkeypatch.setattr("sentence_reading.llm.gcs_sync.download_bytes", download)
    monkeypatch.setattr("sentence_reading.llm.gcs_sync.delete_bytes", delete)
    monkeypatch.setattr(ij, "upload_bytes", upload)
    monkeypatch.setattr(ij, "download_bytes", download)
    monkeypatch.setattr(ij, "delete_bytes", delete)
    agu.reset_gcs_uid()
    yield bucket
    agu.reset_gcs_uid()
    app_mod._JOBS.clear()


@pytest.fixture()
def auth_root(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    root = tmp_path / "root"
    root.mkdir()
    (root / "pyproject.toml").write_text("[project]\nname='t'\n", encoding="utf-8")
    monkeypatch.setattr(aa, "project_root", lambda: root)
    monkeypatch.setattr(aa, "accounts_path", lambda: root / "data" / "auth" / "accounts.json")
    return root


def _register(client: TestClient, email: str) -> None:
    r = client.post(
        "/api/auth/email/register",
        json={"email": email, "password": "password1", "name": "T"},
    )
    assert r.status_code == 200, r.text


def _uid(client: TestClient) -> str:
    return client.get("/api/auth/status").json()["user"]["uid"]


def test_status_resume_skip_flag(fake_gcs, auth_root):
    st = TestClient(app).get("/api/status").json()
    assert st["version"] == "0.3.56"
    assert st["ingest_resume_skip"] is True
    assert st["ingest_checkpoint"] is True


def test_kill_switch_disables_skip(fake_gcs, auth_root, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("ASR_INGEST_RESUME_SKIP", "0")
    assert ij.ingest_resume_skip_enabled() is False
    st = TestClient(app).get("/api/status").json()
    assert st["ingest_resume_skip"] is False


def test_design_112_exists():
    assert DESIGN.is_file()
    text = DESIGN.read_text(encoding="utf-8")
    assert "0.3.26" in text
    assert "ASR_INGEST_RESUME_SKIP" in text
    assert "ingest_payloads" in text


def test_pubspec_pin():
    assert "0.3.56" in PUB.read_text(encoding="utf-8")


def test_payload_owner_isolation(fake_gcs, auth_root):
    client = TestClient(app)
    _register(client, "owner-a@example.com")
    uid_a = _uid(client)
    jid = "job_aabb0011ccdd"
    h = "ab" * 32
    now = datetime.now(timezone.utc).isoformat()
    doc = {
        **irp.base_payload(
            job_id=jid, owner_uid=uid_a, content_hash=h, completed="vision"
        ),
        "pages": ["page one"],
        "text": "page one",
        "updated_at": now,
    }
    assert ij.save_ingest_payload(jid, doc, owner_uid=uid_a) is True
    assert ij.load_ingest_payload(jid, owner_uid=uid_a) is not None
    # EDGE: foreign uid must not read owner payload (path + owner_uid check).
    assert ij.load_ingest_payload(jid, owner_uid="other_uid_not_owner") is None
    obj_a = ij.ingest_payload_object(jid, uid=uid_a)
    assert obj_a is not None
    assert f"users/{uid_a}/" in obj_a
    assert "ingest_payloads" in obj_a


def test_payload_invalid_forces_discard_reason(fake_gcs, auth_root):
    now = datetime(2026, 8, 11, tzinfo=timezone.utc)
    h = "cd" * 32
    good = {
        **irp.base_payload(
            job_id="job_resume002bbb",
            owner_uid="u_test",
            content_hash=h,
            completed="debone",
        ),
        "updated_at": now.isoformat(),
        "sentences": [{"id": "s1", "text": "Hello."}],
    }
    ok, reason = ij.payload_is_valid(
        good, content_hash=h, pipeline_version=PIPELINE_VERSION, now=now
    )
    assert ok is True and reason == "ok"

    # hash mismatch → full restart
    ok, reason = ij.payload_is_valid(
        good, content_hash="ee" * 32, pipeline_version=PIPELINE_VERSION, now=now
    )
    assert ok is False and reason == "hash"

    # pipeline mismatch
    bad = dict(good)
    bad["pipeline_version"] = "rich-v0-fake"
    ok, reason = ij.payload_is_valid(
        bad, content_hash=h, pipeline_version=PIPELINE_VERSION, now=now
    )
    assert ok is False and reason == "pipeline"

    # TTL
    old = dict(good)
    old["updated_at"] = (now - timedelta(days=8)).isoformat()
    ok, reason = ij.payload_is_valid(
        old, content_hash=h, pipeline_version=PIPELINE_VERSION, now=now
    )
    assert ok is False and reason == "ttl"

    # nonsense / path tricks not accepted as completed
    junk = dict(good)
    junk["completed"] = "../etc"
    assert (
        ij.payload_is_valid(
            junk, content_hash=h, pipeline_version=PIPELINE_VERSION, now=now
        )[0]
        is False
    )


def test_vision_resume_start_index(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Resume mid-vision must continue from vision_done, not re-OCR earlier pages."""
    pdf = tmp_path / "x.pdf"
    pdf.write_bytes(b"%PDF-1.4 minimal")
    pages = ["keep0", "keep1", "keep2"]
    calls: list[int] = []

    def fake_render(_path, page_index: int):
        return b"png"

    def fake_ocr(_png, *, page_index: int = 0, page_count: int = 1):
        calls.append(page_index)
        return f"ocr{page_index}"

    monkeypatch.setattr(vo, "render_page_png", fake_render)
    monkeypatch.setattr(vo, "ocr_page_png", fake_ocr)
    monkeypatch.setattr(
        vo,
        "gemini_api_key",
        lambda: "fake-key-not-used",
    )

    resume = {
        "decision": {
            "verdict": "partial_vision",
            "bad_pages": [1, 2],
            "notes": "resume",
            "source": "resume",
        },
        "vision_indices": [1, 2],
        "vision_done": 1,  # page 1 already done
        "pages": ["keep0", "already", "keep2"],
        "warnings": [],
    }
    result = vo.recover_pdf_text(pdf, pages, resume=resume)
    # Only remaining index 2 should be OCR'd.
    assert calls == [2]
    assert result.pages[1] == "already"
    assert result.pages[2] == "ocr2"


def test_vision_checkpoint_callback(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    pdf = tmp_path / "x.pdf"
    pdf.write_bytes(b"%PDF-1.4")
    snaps: list[dict] = []

    monkeypatch.setattr(vo, "render_page_png", lambda *_a, **_k: b"png")
    monkeypatch.setattr(
        vo, "ocr_page_png", lambda *_a, **_k: "x"
    )
    monkeypatch.setattr(vo, "gemini_api_key", lambda: "k")
    monkeypatch.setattr(
        vo,
        "decide_extract_quality",
        lambda _pages: QualityDecision(
            verdict="partial_vision", bad_pages=[0], notes="t", source="test"
        ),
    )
    monkeypatch.setattr(vo, "_select_vision_pages", lambda _d, _n: [0])

    vo.recover_pdf_text(
        pdf,
        ["a"],
        on_checkpoint=lambda d: snaps.append(d),
    )
    assert len(snaps) == 1
    assert snaps[0]["vision_done"] == 1


def test_reclaim_loads_payload_for_owner_only(fake_gcs, auth_root):
    client_a = TestClient(app)
    _register(client_a, "reclaim-a@example.com")
    uid_a = _uid(client_a)

    client_b = TestClient(app)
    _register(client_b, "reclaim-b@example.com")
    uid_b = _uid(client_b)

    jid = "job_ccdd0022eeff"
    h = "ff" * 32
    now = datetime.now(timezone.utc)
    cp = ij.build_checkpoint(
        stage="debone",
        content_hash=h,
        pipeline_version=PIPELINE_VERSION,
        payload_ref=f"{jid}.json",
        now=now,
    )
    pl = {
        **irp.base_payload(
            job_id=jid, owner_uid=uid_a, content_hash=h, completed="debone"
        ),
        "updated_at": now.isoformat(),
        "pages": ["body"],
        "text": "body",
        "sentences": [
            irp.sentence_to_dict(
                Sentence(id="s1", text="One sentence here for resume.")
            )
        ],
        "debone_ok": True,
        "title": "T",
        "references": [],
    }
    job = {
        "percent": 55,
        "stage": "debone",
        "message": "다듬는 중",
        "done": False,
        "error": None,
        "result": None,
        "owner_uid": uid_a,
        "content_hash": h,
        "filename": "paper.pdf",
        "want_translate": False,
        "want_shadowing_chunks": False,
        "checkpoint": cp,
        # expired lease so reclaim can claim
        "lease_until": (now - timedelta(minutes=10)).isoformat(),
        "lease_token": "oldtok",
    }
    assert ij.save_ingest_job(jid, job) is True
    assert ij.save_ingest_payload(jid, pl, owner_uid=uid_a) is True
    # Upload blob required for reclaim.
    assert (
        ij.save_ingest_upload(jid, b"%PDF-1.4 fake", owner_uid=uid_a, suffix=".pdf")
        is True
    )

    # B must not load A's payload via API path tricks.
    r = client_b.get(f"/api/ingest/jobs/{jid}")
    assert r.status_code in (404, 403) or r.json().get("ok") is False

    loaded = ij.load_ingest_payload(jid, owner_uid=uid_b)
    assert loaded is None


def test_sentence_roundtrip_no_secret_leak():
    s = Sentence(
        id="s1",
        text="Hello world.",
        section="body",
        text_ko="안녕",
        text_ko_stage="section",
    )
    d = irp.sentence_to_dict(s)
    back = irp.sentence_from_dict(d)
    assert back is not None
    assert back.text_ko == "안녕"
    # EDGE: empty / wrong shapes fail closed
    assert irp.sentence_from_dict({}) is None
    assert irp.sentence_from_dict("x") is None  # type: ignore[arg-type]


def test_stage_percent_floor_near_resume():
    assert ij.stage_percent_floor("vision") >= 20
    assert ij.stage_percent_floor("debone") >= 48
    assert ij.stage_percent_floor("translate") >= 90
    assert ij.stage_percent_floor("unknown_stage") == 1
