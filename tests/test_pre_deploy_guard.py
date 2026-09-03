"""pre_deploy_guard 계약 (design/155 — stale deploy 차단)."""

from __future__ import annotations

import importlib.util
import sys
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


def test_run_guard_ci_mode_allows_same_version(monkeypatch: pytest.MonkeyPatch) -> None:
    m = _load()
    local = m.read_repo_app_version()
    r = m.run_guard(live_data={"version": local}, ci_mode=True, skip_fetch=True)
    assert r["ok"] is True, r["errors"]
    assert r.get("mode") == "ci"


def test_deploy_script_wires_guard() -> None:
    text = (ROOT / "scripts" / "deploy_cloud_run.sh").read_text(encoding="utf-8")
    assert "pre_deploy_guard.py" in text
    assert "ASR_DEPLOY_GIT_SHA" in text
    assert "ASR_SKIP_DEPLOY_GUARD" in text
    assert "post-deploy verify" in text
    assert "verify_live_status.py" in text


def test_session_and_hook_scripts_exist() -> None:
    assert (ROOT / "scripts" / "session_freshness_guard.py").is_file()
    hook = (ROOT / "scripts" / "hook_block_stale_asr_deploy.py").read_text(
        encoding="utf-8"
    )
    assert "pre_deploy_guard" in hook
    assert "permission" in hook
    assert "local_version_downgrade" in hook or "run_guard" in hook
    design = (ROOT / "docs" / "design" / "155-deploy-live-guard.md").read_text(
        encoding="utf-8"
    )
    assert "session_freshness_guard" in design
    assert "hook_block_stale_asr_deploy" in design
    rule = (ROOT / ".cursor" / "rules" / "deploy-live-guard.mdc").read_text(
        encoding="utf-8"
    )
    assert "session_freshness_guard" in rule
    assert "alwaysApply: true" in rule


def test_design_173_implementation_hazards_locked() -> None:
    """design/173 — hazards + observability baseline must stay in repo."""
    path = ROOT / "docs" / "design" / "173-capacity-isolation-roadmap.md"
    assert path.is_file()
    text = path.read_text(encoding="utf-8")
    assert "Implementation hazards (locked" in text
    assert "Observability baseline (locked" in text
    assert "capacity_baseline_snapshot.py" in text
    assert "invalidate 필수 write 경로" in text
    assert "173a → 173b → 173c" in text
    assert "Deny 후에도 TTL 동안 유료 통과" in text
    assert "ASR_ACCESS_GATE_TTL_S=0" in text
    assert (ROOT / "scripts" / "capacity_baseline_snapshot.py").is_file()
    rule = (ROOT / ".cursor" / "rules" / "deploy-live-guard.mdc").read_text(
        encoding="utf-8"
    )
    assert "173-capacity-isolation-roadmap" in rule
    assert "Implementation hazards" in rule


def test_capacity_baseline_snapshot_smoke(monkeypatch: pytest.MonkeyPatch) -> None:
    """Snapshot builds without network when status/evidence mocked."""
    import importlib.util

    script = ROOT / "scripts" / "capacity_baseline_snapshot.py"
    spec = importlib.util.spec_from_file_location("capacity_baseline", script)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    monkeypatch.setattr(
        mod,
        "fetch_status",
        lambda url: {
            "ok": True,
            "version": "0.3.148",
            "deploy_git_sha": "abc",
            "access_gate_enabled": True,
        },
    )
    monkeypatch.setattr(mod, "_cloud_run_spec", lambda: {"cpu": "1", "memory": "1Gi"})
    monkeypatch.setattr(
        mod,
        "_load_evidence_rows",
        lambda **k: [
            {
                "kind": "client_api_timeout",
                "details": {"route": "access_status"},
                "ts": "2026-01-01T00:00:00Z",
            }
        ],
    )
    snap = mod.build_snapshot(
        status_url="https://example.invalid/api/status",
        since_raw="24h",
        bucket_prefix="gs://test",
    )
    assert snap["schema"] == "asr_capacity_baseline_v1"
    assert snap["evidence"]["access_auth_timeout_total"] == 1
    assert snap["evidence"]["client_api_timeout_by_route"]["access_status"] == 1


def test_hook_emits_deny_json_for_stale_asr_deploy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Contract: hook stdout is one permission JSON object (failClosed-safe)."""
    import io
    import json
    from importlib.machinery import SourceFileLoader

    path = ROOT / "scripts" / "hook_block_stale_asr_deploy.py"
    mod = SourceFileLoader("hook_asr", str(path)).load_module()
    payload = {
        "command": (
            f'cd "{ROOT}" && bash scripts/' + "deploy_" + "cloud_run.sh"
        ),
        "working_directory": str(ROOT),
    }
    # Force guard failure without network: downgrade vs fake live.
    real_load = mod._load_guard

    def fake_load(root):
        g = real_load(root)
        monkeypatch.setattr(
            g,
            "run_guard",
            lambda **k: {
                "ok": False,
                "local_version": "0.0.1",
                "live_version": "9.9.9",
                "commits_behind_remote": 0,
                "errors": ["local_version_downgrade:0.0.1_lt_live_9.9.9"],
            },
        )
        return g

    monkeypatch.setattr(mod, "_load_guard", fake_load)
    monkeypatch.setattr(mod, "_find_asr_root", lambda c, w: ROOT)
    buf = io.StringIO(json.dumps(payload))
    monkeypatch.setattr(sys, "stdin", buf)
    out = io.StringIO()
    monkeypatch.setattr(sys, "stdout", out)
    code = mod.main()
    assert code == 0
    data = json.loads(out.getvalue().strip())
    assert data["permission"] == "deny"
    assert "BLOCKED" in data.get("user_message", "")


def test_workflow_wires_guard() -> None:
    ci = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    deploy = (ROOT / ".github" / "workflows" / "deploy-cloud-run.yml").read_text(
        encoding="utf-8"
    )
    assert "pre_deploy_guard.py" in ci
    assert "--ci" in ci
    assert "pre_deploy_guard.py" in deploy
    assert "fetch-depth: 0" in deploy


def test_status_exposes_deploy_git_sha(monkeypatch: pytest.MonkeyPatch) -> None:
    from fastapi.testclient import TestClient

    from sentence_reading.api.app import app

    monkeypatch.setenv("ASR_DEPLOY_GIT_SHA", "abc123deadbeef")
    st = TestClient(app).get("/api/status").json()
    assert st["deploy_git_sha"] == "abc123deadbeef"
