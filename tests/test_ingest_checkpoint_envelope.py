# -*- coding: utf-8 -*-
"""design/110 — ingest checkpoint envelope (accept/discard; skip later)."""
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
from sentence_reading.llm.typography import PIPELINE_VERSION

ROOT = Path(__file__).resolve().parents[1]
DESIGN = ROOT / "docs" / "design" / "110-ingest-checkpoint-envelope.md"
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
    monkeypatch.setenv("ASR_AUTH_SECRET", "checkpoint-secret")
    monkeypatch.setenv("ASR_EMAIL_AUTH", "1")
    monkeypatch.setenv("ASR_INGEST_JOB_RECLAIM", "1")
    monkeypatch.setenv("ASR_INGEST_CHECKPOINT", "1")
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


def test_status_checkpoint_flag(fake_gcs, auth_root):
    st = TestClient(app).get("/api/status").json()
    assert st["version"] == "0.3.54"
    assert st["ingest_checkpoint"] is True
    assert st["pipeline_version"] == PIPELINE_VERSION


def test_design_110_exists():
    assert DESIGN.is_file()
    text = DESIGN.read_text(encoding="utf-8")
    # WHY: chip 110 shipped at 0.3.24 — design pin is historical.
    assert "0.3.24" in text
    assert "checkpoint" in text.lower()
    assert "ASR_INGEST_CHECKPOINT" in text
    assert "스킵" in text or "skip" in text.lower()


def test_pubspec_pin():
    assert "0.3.54" in PUB.read_text(encoding="utf-8")


def test_checkpoint_valid_and_discard_reasons():
    now = datetime(2026, 8, 11, tzinfo=timezone.utc)
    h = "ab" * 32
    good = ij.build_checkpoint(
        stage="vision",
        content_hash=h,
        pipeline_version=PIPELINE_VERSION,
        cursor={"done": 12, "total": 40},
        now=now,
    )
    ok, reason = ij.checkpoint_is_valid(
        good, content_hash=h, pipeline_version=PIPELINE_VERSION, now=now
    )
    assert ok is True and reason == "ok"
    assert "12/40" in ij.checkpoint_resume_message(good)

    # TTL discard
    old = dict(good)
    old["updated_at"] = (now - timedelta(days=8)).isoformat()
    ok, reason = ij.checkpoint_is_valid(
        old, content_hash=h, pipeline_version=PIPELINE_VERSION, now=now
    )
    assert ok is False and reason == "ttl"

    # pipeline mismatch
    bad_pipe = dict(good)
    bad_pipe["pipeline_version"] = "rich-v0-fake"
    ok, reason = ij.checkpoint_is_valid(
        bad_pipe, content_hash=h, pipeline_version=PIPELINE_VERSION, now=now
    )
    assert ok is False and reason == "pipeline"

    # hash mismatch
    ok, reason = ij.checkpoint_is_valid(
        good, content_hash="cd" * 32, pipeline_version=PIPELINE_VERSION, now=now
    )
    assert ok is False and reason == "hash"

    # empty / nonsense
    assert ij.checkpoint_is_valid(None, content_hash=h, pipeline_version=PIPELINE_VERSION)[0] is False
    assert ij.checkpoint_is_valid("x", content_hash=h, pipeline_version=PIPELINE_VERSION)[0] is False
    assert ij.checkpoint_is_valid({"v": 1}, content_hash="", pipeline_version=PIPELINE_VERSION)[0] is False


def test_serialize_persists_want_flags_and_checkpoint(fake_gcs, auth_root):
    client = TestClient(app)
    _register(client, "owner-cp@example.com")
    uid = client.get("/api/auth/status").json()["user"]["uid"]
    jid = "job_aabbccddee01"
    h = "ef" * 32
    cp = ij.build_checkpoint(
        stage="debone",
        content_hash=h,
        pipeline_version=PIPELINE_VERSION,
        cursor={"done": 3, "total": 10},
    )
    job = {
        "percent": 60,
        "stage": "debone",
        "message": "다듬는 중 3/10",
        "done": False,
        "error": None,
        "result": None,
        "owner_uid": uid,
        "content_hash": h,
        "filename": "paper.pdf",
        "want_translate": False,
        "want_shadowing_chunks": True,
        "checkpoint": cp,
    }
    assert ij.save_ingest_job(jid, job) is True
    loaded = ij.load_ingest_job(jid, owner_uid=uid)
    assert loaded is not None
    assert loaded["want_translate"] is False
    assert loaded["want_shadowing_chunks"] is True
    assert loaded["checkpoint"]["stage"] == "debone"
    assert loaded["checkpoint"]["cursor"]["done"] == 3
    # EDGE: foreign uid must not see the job (or its checkpoint).
    assert ij.load_ingest_job(jid, owner_uid="other_uid_xxx") is None


def test_public_job_view_exposes_hint_not_body():
    view = ij.public_job_view(
        "job_aabbccddeeff",
        {
            "percent": 30,
            "stage": "vision",
            "message": "비전 중",
            "done": False,
            "content_hash": "aa" * 32,
            "checkpoint": {
                "v": 1,
                "pipeline_version": PIPELINE_VERSION,
                "stage": "vision",
                "content_hash": "aa" * 32,
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "cursor": {"done": 12, "total": 40},
            },
        },
    )
    assert view["checkpoint_stage"] == "vision"
    assert view["checkpoint_cursor"] == {"done": 12, "total": 40}
    # Never dump paper text fields from checkpoint path.
    assert "text" not in view
    assert "sentences" not in view


def test_kill_switch_disables_checkpoint(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("ASR_INGEST_CHECKPOINT", "0")
    assert ij.ingest_checkpoint_enabled() is False
    h = "ab" * 32
    cp = ij.build_checkpoint(
        stage="vision",
        content_hash=h,
        pipeline_version=PIPELINE_VERSION,
    )
    ok, reason = ij.checkpoint_is_valid(
        cp, content_hash=h, pipeline_version=PIPELINE_VERSION
    )
    assert ok is False and reason == "disabled"


def test_reclaim_message_keeps_valid_checkpoint(
    fake_gcs, auth_root, monkeypatch: pytest.MonkeyPatch
):
    """Owner poll reclaim: valid CP+payload → resume hint; missing payload → restart."""
    client = TestClient(app)
    _register(client, "resume-hint@example.com")
    uid = client.get("/api/auth/status").json()["user"]["uid"]
    jid = "job_abc123abc123"
    h = "aa" * 32
    past = (datetime.now(timezone.utc) - timedelta(seconds=200)).isoformat()
    now = datetime.now(timezone.utc)
    cp = ij.build_checkpoint(
        stage="vision",
        content_hash=h,
        pipeline_version=PIPELINE_VERSION,
        cursor={"done": 12, "total": 40},
        payload_ref=f"{jid}.json",
        now=now,
    )
    pl = {
        "v": 1,
        "job_id": jid,
        "owner_uid": uid,
        "pipeline_version": PIPELINE_VERSION,
        "content_hash": h,
        "completed": "vision",
        "updated_at": now.isoformat(),
        "pages": ["p"],
        "text": "p",
    }
    job = {
        "percent": 28,
        "stage": "vision",
        "message": "비전 중",
        "done": False,
        "error": None,
        "result": None,
        "owner_uid": uid,
        "content_hash": h,
        "filename": "long.pdf",
        "lease_until": past,
        "want_translate": False,
        "checkpoint": cp,
    }
    assert ij.save_ingest_job(jid, job) is True
    assert ij.save_ingest_payload(jid, pl, owner_uid=uid) is True
    assert ij.save_ingest_upload(
        jid, b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n", owner_uid=uid
    )

    async def fake_run(job_id, tmp_path, filename, kind, **kwargs):
        j = app_mod._JOBS.get(job_id)
        if j is not None:
            j["done"] = True
            j["percent"] = 100
            j["_local_running"] = False
            j["result"] = {
                "ok": True,
                "cache_id": "cache_x",
                "session_id": "ses_x",
            }

    monkeypatch.setattr(app_mod, "_run_ingest_job", fake_run)
    app_mod._JOBS.clear()
    st = client.get(f"/api/ingest/jobs/{jid}")
    assert st.status_code == 200, st.text
    body = st.json()
    msg = body.get("message") or ""
    assert "이어받을 지점" in msg
    assert "12/40" in msg
    mem = app_mod._JOBS[jid]
    assert isinstance(mem.get("checkpoint"), dict)
    assert mem["checkpoint"]["stage"] == "vision"
    assert isinstance(mem.get("_resume_payload"), dict)


def test_reclaim_discards_stale_checkpoint(
    fake_gcs, auth_root, monkeypatch: pytest.MonkeyPatch
):
    client = TestClient(app)
    _register(client, "stale-cp@example.com")
    uid = client.get("/api/auth/status").json()["user"]["uid"]
    jid = "job_def456def456"
    h = "bb" * 32
    past = (datetime.now(timezone.utc) - timedelta(seconds=200)).isoformat()
    cp = ij.build_checkpoint(
        stage="vision",
        content_hash=h,
        pipeline_version=PIPELINE_VERSION,
        cursor={"done": 5, "total": 10},
        now=datetime.now(timezone.utc) - timedelta(days=10),
    )
    job = {
        "percent": 25,
        "stage": "vision",
        "message": "비전 중",
        "done": False,
        "error": None,
        "result": None,
        "owner_uid": uid,
        "content_hash": h,
        "filename": "old.pdf",
        "lease_until": past,
        "checkpoint": cp,
    }
    assert ij.save_ingest_job(jid, job) is True
    assert ij.save_ingest_upload(jid, b"%PDF-1.4 stale", owner_uid=uid)

    async def fake_run(job_id, tmp_path, filename, kind, **kwargs):
        j = app_mod._JOBS.get(job_id)
        if j is not None:
            j["done"] = True
            j["_local_running"] = False
            j["result"] = {"ok": True, "cache_id": "c", "session_id": "s"}

    monkeypatch.setattr(app_mod, "_run_ingest_job", fake_run)
    app_mod._JOBS.clear()
    st = client.get(f"/api/ingest/jobs/{jid}")
    assert st.status_code == 200
    body = st.json()
    assert "처리 다시 시작" in (body.get("message") or "")
    assert app_mod._JOBS[jid].get("checkpoint") is None
