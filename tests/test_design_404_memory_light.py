"""design/404 - click jobs wait for memory and size their knobs to what is free."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CLICK = ROOT / "click"


def _load(name: str):
    sys.path.insert(0, str(CLICK))
    spec = importlib.util.spec_from_file_location(f"asr_click_{name}", CLICK / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def test_knobs_follow_free_memory():
    mem = _load("_mem")
    assert mem.flutter_test_workers(0.3, 4) == 1
    assert mem.flutter_test_workers(1.3, 4) == 2
    assert mem.flutter_test_workers(9.0, 4) == 4
    assert mem.apk_heap_gb(2.0) == 2.0
    assert mem.apk_heap_gb(4.8) == 3.0
    assert mem.apk_heap_gb(20.0) == 8.0


def test_need_learns_fixed_steps_but_not_scaled(tmp_path):
    mem = _load("_mem")
    h = mem.History(tmp_path / "h.json")
    assert h.need("web_build") == mem.MIN_NEED_GB["web_build"]
    h.record("web_build", 3.0)
    assert h.need("web_build") == 3.6
    h.record("pytest", 0.2)
    assert h.need("pytest") == mem.MIN_NEED_GB["pytest"]
    h.record("apk", 6.0)
    assert h.need("apk") == mem.MIN_NEED_GB["apk"]
    again = mem.History(tmp_path / "h.json")
    assert again.data["web_build"] == [3.0]
    for _ in range(9):
        again.record("web_build", 1.0)
    assert len(again.data["web_build"]) == mem.HISTORY_KEEP


def test_light_waits_until_memory_frees(monkeypatch):
    mem = _load("_mem")
    seq = iter([0.2, 0.5, 2.0])
    monkeypatch.setattr(mem, "usable_gb", lambda free=None: next(seq))
    monkeypatch.setattr(mem.time, "sleep", lambda s: None)
    said, status = [], []
    waited = mem.wait_for(1.5, "앱 빌드", said.append, status.append, lambda: ["sim_a"])
    assert waited >= 0
    assert said and "빨간불" in said[0] and "sim_a" in said[0]
    assert status and "앱 빌드" in status[0]


def test_light_passes_at_once_when_free(monkeypatch):
    mem = _load("_mem")
    monkeypatch.setattr(mem, "usable_gb", lambda free=None: 5.0)
    said = []
    assert mem.wait_for(1.0, "x", said.append, said.append, lambda: []) < 0.1
    assert said == []


def test_every_step_goes_through_the_light():
    src = (CLICK / "_run.py").read_text(encoding="utf-8")
    run_body = src[src.index("    def run(") : src.index("def _decode")]
    assert "self.light(title, step)" in run_body
    assert "subprocess.Popen(" in run_body
    assert run_body.index("self.light(title, step)") < run_body.index("subprocess.Popen(")
    assert "input(" not in src
    apk = src[src.index("def build_apk") : src.index("def job_ship_install")]
    assert "GRADLE_OPTS" in apk and "-Dorg.gradle.jvmargs=-Xmx" in apk
    assert apk.count("stop_gradle_daemons()") == 2
    assert "--concurrency=" in src


def test_selftest_never_waits():
    src = (CLICK / "_run.py").read_text(encoding="utf-8")
    assert 'if step == "none":' in src
    body = src[src.index("def job_selftest") : src.index("JOBS = {")]
    assert 'step="none"' in body
