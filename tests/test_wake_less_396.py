"""design/396 — callers that wake a scaled-to-zero API without a person."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient

from sentence_reading.api.app import app
from sentence_reading.llm.login_required import is_login_public_path

ROOT = Path(__file__).resolve().parents[1]


def _guard_mod():
    spec = importlib.util.spec_from_file_location(
        "session_freshness_guard_396", ROOT / "scripts" / "session_freshness_guard.py"
    )
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def _desc(*, ready="r2", created="r2", percent=100, latest=True, version="0.3.436"):
    env = [{"name": "ASR_DEPLOY_GIT_SHA", "value": "abc123"}]
    if version:
        env.append({"name": "ASR_RELEASE_VERSION", "value": version})
    return {
        "status": {
            "latestReadyRevisionName": ready,
            "latestCreatedRevisionName": created,
            "traffic": [{"percent": percent, "latestRevision": latest}],
        },
        "spec": {"template": {"spec": {"containers": [{"env": env}]}}},
    }


def test_parse_service_reads_release_env() -> None:
    mod = _guard_mod()
    assert mod.parse_service(_desc()) == {"version": "0.3.436", "deploy_git_sha": "abc123"}


def test_parse_service_refuses_uncertain_state() -> None:
    mod = _guard_mod()
    assert mod.parse_service(_desc(created="r3")) is None
    assert mod.parse_service(_desc(percent=50)) is None
    assert mod.parse_service(_desc(latest=False)) is None
    assert mod.parse_service(_desc(version="")) is None
    assert mod.parse_service({}) is None


def test_live_from_service_falls_back_on_failure() -> None:
    mod = _guard_mod()
    assert mod.live_from_service(run=lambda *a, **k: SimpleNamespace(returncode=1, stdout="")) is None
    assert mod.live_from_service(run=lambda *a, **k: SimpleNamespace(returncode=0, stdout="not json")) is None

    def boom(*a, **k):
        raise FileNotFoundError("gcloud")

    assert mod.live_from_service(run=boom) is None
    ok = SimpleNamespace(returncode=0, stdout=json.dumps(_desc()))
    assert mod.live_from_service(run=lambda *a, **k: ok)["version"] == "0.3.436"


def test_freshness_passes_service_env_to_guard(monkeypatch, capsys) -> None:
    mod = _guard_mod()
    seen = {}

    class Guard:
        @staticmethod
        def run_guard(**kw):
            seen.update(kw)
            return {"errors": [], "live_version": kw["live_data"]["version"]}

    monkeypatch.delenv("ASR_SKIP_DEPLOY_GUARD", raising=False)
    monkeypatch.delenv("ASR_FRESHNESS_LIVE", raising=False)
    monkeypatch.setattr(mod, "_load_guard", lambda: Guard)
    monkeypatch.setattr(mod, "live_from_service", lambda: {"version": "0.3.436", "deploy_git_sha": "abc"})
    assert mod.main([]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["live_source"] == "service_env"
    assert seen["live_data"]["version"] == "0.3.436"


def test_freshness_http_switch(monkeypatch, capsys) -> None:
    mod = _guard_mod()

    class Guard:
        @staticmethod
        def run_guard(**kw):
            assert kw["live_data"] is None
            return {"errors": []}

    monkeypatch.delenv("ASR_SKIP_DEPLOY_GUARD", raising=False)
    monkeypatch.setenv("ASR_FRESHNESS_LIVE", "http")
    monkeypatch.setattr(mod, "_load_guard", lambda: Guard)
    monkeypatch.setattr(mod, "live_from_service", lambda: (_ for _ in ()).throw(AssertionError("asked")))
    assert mod.main([]) == 0
    assert json.loads(capsys.readouterr().out)["live_source"] == "http"


def test_robots_txt_disallows_all() -> None:
    res = TestClient(app).get("/robots.txt")
    assert res.status_code == 200
    assert res.text == "User-agent: *\nDisallow: /\n"
    assert res.headers["x-robots-tag"] == "noindex, nofollow"
    assert is_login_public_path("/robots.txt")


def test_index_says_noindex() -> None:
    res = TestClient(app).get("/")
    assert res.headers.get("x-robots-tag") == "noindex, nofollow"


def test_mobile_loops_check_the_screen() -> None:
    lib = ROOT / "mobile" / "lib"
    client = (lib / "api" / "client.dart").read_text(encoding="utf-8")
    assert "await pollPause(pollInterval)" in client
    assert "'poll_parked'" in client
    bus = (lib / "services" / "evidence_bus.dart").read_text(encoding="utf-8")
    assert "AppForeground.instance.resting" in bus
    lc = (lib / "state" / "library_controller.dart").read_text(encoding="utf-8")
    assert lc.count("if (AppForeground.instance.away) return;") == 2
    main = (lib / "main.dart").read_text(encoding="utf-8")
    assert "AppForeground.instance.bind();" in main
