# -*- coding: utf-8 -*-
"""design/174 — worker GCS uid scope + papers upload fail + library list miss."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest


def test_gcs_uid_scope_restores_previous():
    from sentence_reading.llm import auth_google as ag

    ag.reset_gcs_uid()
    ag.set_gcs_uid("111111111111111111111")
    with ag.gcs_uid_scope("222222222222222222222"):
        assert ag.current_gcs_uid() == "222222222222222222222"
    assert ag.current_gcs_uid() == "111111111111111111111"
    ag.reset_gcs_uid()


def test_gcs_uid_scope_sets_from_empty():
    from sentence_reading.llm import auth_google as ag

    ag.reset_gcs_uid()
    with ag.gcs_uid_scope("333333333333333333333"):
        assert ag.current_gcs_uid() == "333333333333333333333"
    assert ag.current_gcs_uid() is None


def test_personal_object_name_none_without_uid_when_auth_on(monkeypatch):
    from sentence_reading.llm import auth_google as ag
    from sentence_reading.llm import gcs_sync as gs

    ag.reset_gcs_uid()
    monkeypatch.setattr(ag, "auth_enabled", lambda: True)
    assert gs.personal_object_name("papers", "index.json") is None


def test_personal_object_name_with_uid_scope(monkeypatch):
    from sentence_reading.llm import auth_google as ag
    from sentence_reading.llm import gcs_sync as gs

    monkeypatch.setattr(ag, "auth_enabled", lambda: True)
    monkeypatch.setattr(
        gs,
        "object_name",
        lambda *parts: "/".join(("asr",) + tuple(str(p) for p in parts)),
    )
    ag.reset_gcs_uid()
    with ag.gcs_uid_scope("444444444444444444444"):
        path = gs.personal_object_name("papers", "index.json")
    assert path == "asr/users/444444444444444444444/papers/index.json"
    assert ag.current_gcs_uid() is None


def test_ensure_paper_false_when_auth_no_uid(monkeypatch):
    from sentence_reading.llm import auth_google as ag
    from sentence_reading.llm import papers_gcs as pg

    ag.reset_gcs_uid()
    monkeypatch.setattr(ag, "auth_enabled", lambda: True)
    monkeypatch.setattr(pg, "gcs_client_ready", lambda: (True, "ok"))
    monkeypatch.setattr(pg, "gcs_config", lambda: type("C", (), {"enabled": True})())
    assert pg.ensure_paper_in_remote_index("abcd1234efgh") is False


def test_ensure_paper_true_when_gcs_off(monkeypatch):
    from sentence_reading.llm import papers_gcs as pg

    monkeypatch.setattr(pg, "gcs_client_ready", lambda: (False, "off"))
    monkeypatch.setattr(pg, "gcs_config", lambda: type("C", (), {"enabled": False})())
    assert pg.ensure_paper_in_remote_index("abcd1234efgh") is True


def test_papers_upload_fail_and_library_list_miss_in_allowlist():
    from sentence_reading.llm.evidence_kinds import ALLOWED_KINDS
    from sentence_reading.llm.evidence_floor import FROZEN_KINDS

    assert "papers_upload_fail" in ALLOWED_KINDS
    assert "library_list_miss" in ALLOWED_KINDS
    assert "papers_upload_fail" in FROZEN_KINDS
    assert "library_list_miss" in FROZEN_KINDS


def test_run_ingest_job_binds_owner_uid(monkeypatch):
    """Worker path must see owner uid inside the body (design/174)."""
    from sentence_reading.api import app as app_mod
    from sentence_reading.llm import auth_google as ag

    seen: list[str | None] = []

    async def fake_body(job_id, tmp_path, filename, kind, **kwargs):
        seen.append(ag.current_gcs_uid())

    async def fake_heartbeat(_job_id: str):
        try:
            while True:
                await asyncio.sleep(3600)
        except asyncio.CancelledError:
            raise

    monkeypatch.setattr(app_mod, "_run_ingest_job_body", fake_body)
    monkeypatch.setattr(app_mod, "_ingest_lease_heartbeat", fake_heartbeat)
    app_mod._JOBS["job_aabbccddeeff"] = {
        "owner_uid": "555555555555555555555",
        "percent": 1,
    }
    ag.reset_gcs_uid()

    asyncio.run(
        app_mod._run_ingest_job(
            "job_aabbccddeeff",
            Path("x.pdf"),
            "x.pdf",
            "pdf",
        )
    )
    assert seen == ["555555555555555555555"]
    assert ag.current_gcs_uid() is None


def test_status_version_0_3_156():
    from fastapi.testclient import TestClient
    from sentence_reading.api.app import app

    client = TestClient(app)
    st = client.get("/api/status").json()
    assert st["version"] == "0.3.156"


def test_cache_papers_fresh_invalidates(monkeypatch):
    from sentence_reading.api import app as app_mod
    from sentence_reading.llm import papers_gcs as pg

    calls = {"n": 0}

    def inv():
        calls["n"] += 1

    monkeypatch.setattr(pg, "invalidate_remote_index_cache", inv)
    monkeypatch.setattr(pg, "list_merged_paper_entries", lambda: [])

    app_mod.cache_papers(fresh=0)
    assert calls["n"] == 0
    app_mod.cache_papers(fresh=1)
    assert calls["n"] == 1


def test_mobile_library_list_miss_kind_in_dart():
    from pathlib import Path

    dart = (
        Path(__file__).resolve().parents[1]
        / "mobile"
        / "lib"
        / "services"
        / "evidence_kinds.dart"
    ).read_text(encoding="utf-8")
    assert "library_list_miss" in dart
    assert "papers_upload_fail" in dart
    ctrl = (
        Path(__file__).resolve().parents[1]
        / "mobile"
        / "lib"
        / "state"
        / "library_controller.dart"
    ).read_text(encoding="utf-8")
    assert "library_list_miss" in ctrl
    assert "_confirmCacheInLibrary" in ctrl
