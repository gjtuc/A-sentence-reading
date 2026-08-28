"""pre_deploy_guard 계약 (design/155 — stale deploy 차단)."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "pre_deploy_guard.py"


def _load():
    spec = importlib.util.spec_from_file_location("pre_deploy_guard", SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _clean_git(monkeypatch: pytest.MonkeyPatch, mod) -> None:
    monkeypatch.setattr(mod, "git_fetch", lambda *a, **k: [])
    monkeypatch.setattr(mod, "git_behind_remote", lambda *a, **k: ([], 0))
    monkeypatch.setattr(mod, "git_dirty", lambda: False)
    monkeypatch.setattr(mod, "git_head_sha", lambda **k: "deadbeef0001")


def test_compare_semver() -> None:
    m = _load()
    assert m.compare_semver("0.3.81", "0.3.80") == 1
    assert m.compare_semver("0.3.80", "0.3.81") == -1
    assert m.compare_semver("0.3.81", "0.3.81") == 0
    assert m.compare_semver("0.3.82", "0.3.81") == 1


def test_run_guard_blocks_downgrade(monkeypatch: pytest.MonkeyPatch) -> None:
    m = _load()
    _clean_git(monkeypatch, m)
    r = m.run_guard(live_data={"version": "9.9.9"}, skip_fetch=True)
    assert r["ok"] is False
    assert any("downgrade" in e for e in r["errors"])


def test_run_guard_blocks_same_version(monkeypatch: pytest.MonkeyPatch) -> None:
    m = _load()
    _clean_git(monkeypatch, m)
    local = m.read_repo_app_version()
    r = m.run_guard(live_data={"version": local}, skip_fetch=True)
    assert r["ok"] is False
    assert any("same_version" in e for e in r["errors"])


def test_run_guard_allows_bump(monkeypatch: pytest.MonkeyPatch) -> None:
    m = _load()
    _clean_git(monkeypatch, m)
    local = m.read_repo_app_version()
    live = m.parse_semver(local)
    assert live is not None
    parts = list(live)
    parts[-1] = max(0, parts[-1] - 1)
    older = ".".join(str(p) for p in parts)
    r = m.run_guard(live_data={"version": older}, skip_fetch=True)
    assert r["ok"] is True, r["errors"]


def test_run_guard_blocks_already_deployed_sha(monkeypatch: pytest.MonkeyPatch) -> None:
    m = _load()
    _clean_git(monkeypatch, m)
    local = m.read_repo_app_version()
    parts = list(m.parse_semver(local) or (0, 3, 0))
    parts[-1] = max(0, parts[-1] - 1)
    older = ".".join(str(p) for p in parts)
    r = m.run_guard(
        live_data={"version": older, "deploy_git_sha": "deadbeef0001"},
        skip_fetch=True,
    )
    assert r["ok"] is False
    assert any("already_deployed_sha" in e for e in r["errors"])


def test_mobile_app_version_match() -> None:
    m = _load()
    assert m.read_repo_app_version() == m.read_pubspec_version()


def test_deploy_script_wires_guard() -> None:
    text = (ROOT / "scripts" / "deploy_cloud_run.sh").read_text(encoding="utf-8")
    assert "pre_deploy_guard.py" in text
    assert "ASR_DEPLOY_GIT_SHA" in text
    assert "ASR_SKIP_DEPLOY_GUARD" in text


def test_workflow_wires_guard() -> None:
    text = (ROOT / ".github" / "workflows" / "deploy-cloud-run.yml").read_text(
        encoding="utf-8"
    )
    assert "pre_deploy_guard.py" in text
    assert "fetch-depth: 0" in text


def test_status_exposes_deploy_git_sha(monkeypatch: pytest.MonkeyPatch) -> None:
    from fastapi.testclient import TestClient

    from sentence_reading.api.app import app

    monkeypatch.setenv("ASR_DEPLOY_GIT_SHA", "abc123deadbeef")
    st = TestClient(app).get("/api/status").json()
    assert st["deploy_git_sha"] == "abc123deadbeef"
