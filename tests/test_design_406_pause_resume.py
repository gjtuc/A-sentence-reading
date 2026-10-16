"""design/406 - a red light mid-step suspends the step; green resumes it, as often as needed."""

from __future__ import annotations

import importlib.util
import subprocess
import sys
import time
from pathlib import Path

import psutil

ROOT = Path(__file__).resolve().parent.parent
CLICK = ROOT / "click"


def _load(name: str):
    sys.path.insert(0, str(CLICK))
    spec = importlib.util.spec_from_file_location(f"asr_click406_{name}", CLICK / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


class FakeProc:
    def __init__(self, pid: int) -> None:
        self.pid = pid
        self.suspended = 0
        self.resumed = 0

    def suspend(self) -> None:
        self.suspended += 1

    def resume(self) -> None:
        self.resumed += 1


def test_red_pauses_green_resumes_and_repeats():
    mem = _load("_mem")
    w = mem.Watch(pid=0, pausable=True)
    a, b = FakeProc(1), FakeProc(2)
    stock = lambda: ["sim_growth_redis_1"]  # noqa: E731
    assert w.gate(2.0, [a], stock) == ""
    assert w.gate(-0.3, [a], stock) == "pause"
    assert w.paused and a.suspended == 1
    assert w.gate(0.2, [a, b], stock) == ""
    assert b.suspended == 1 and a.suspended == 1
    assert w.gate(mem.RESUME_AT_GB, [a, b], stock) == "resume"
    assert not w.paused and a.resumed == 1 and b.resumed == 1
    assert w.gate(-0.1, [a, b], stock) == "pause"
    assert w.gate(1.0, [a, b], stock) == "resume"
    assert w.pauses == 2 and a.suspended == 2 and a.resumed == 2


def test_no_pause_without_stock_job_or_for_unpausable_steps():
    mem = _load("_mem")
    a = FakeProc(1)
    assert mem.Watch(pid=0, pausable=True).gate(-1.0, [a], lambda: []) == ""
    assert mem.Watch(pid=0, pausable=False).gate(-1.0, [a], lambda: ["sim"]) == ""
    assert a.suspended == 0
    assert {"ship", "probe", "light", "none"}.isdisjoint(mem.PAUSABLE)
    assert {"pytest", "flutter_test", "web_build", "apk"} <= mem.PAUSABLE


def test_paused_step_resumes_when_stock_job_ends(monkeypatch):
    mem = _load("_mem")
    monkeypatch.setattr(mem, "OTHERS_EVERY_S", 0)
    running = iter([["sim"], []])
    w = mem.Watch(pid=0, pausable=True)
    a = FakeProc(1)
    assert w.gate(-0.5, [a], lambda: next(running)) == "pause"
    assert w.gate(-0.5, [a], lambda: next(running)) == "resume"
    assert a.resumed == 1


def test_stop_never_leaves_a_step_suspended(tmp_path: Path):
    mem = _load("_mem")
    w = mem.Watch(pid=0, pausable=True, procs_file=tmp_path / "procs")
    a = FakeProc(1)
    w.gate(-1.0, [a], lambda: ["sim"])
    w.stop()
    assert a.resumed == 1 and not w.paused and w.paused_s >= 0


def test_real_process_suspends_and_resumes(tmp_path: Path):
    mem = _load("_mem")
    out = tmp_path / "ticks"
    code = "import time,sys\nn=0\nwhile True:\n    n+=1\n    open(sys.argv[1],'w').write(str(n))\n    time.sleep(0.05)\n"
    child = subprocess.Popen([sys.executable, "-c", code, str(out)])
    try:
        while not out.exists():
            time.sleep(0.05)
        w = mem.Watch(pid=child.pid, pausable=True)
        assert w.gate(-1.0, w.tree(), lambda: ["sim"]) == "pause"
        time.sleep(0.3)
        frozen = out.read_text()
        time.sleep(0.5)
        assert out.read_text() == frozen
        assert w.gate(1.0, w.tree(), lambda: ["sim"]) == "resume"
        time.sleep(0.5)
        assert out.read_text() != frozen
    finally:
        child.kill()


def test_leftovers_of_a_dead_window_are_killed(tmp_path: Path):
    mem = _load("_mem")
    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
    other = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
    try:
        ctime = psutil.Process(child.pid).create_time()
        procs = tmp_path / "procs"
        procs.write_text(f"{child.pid} {ctime:.3f}\n{other.pid} 1.000", encoding="utf-8")
        assert mem.kill_leftovers(procs) == 1
        assert child.wait(timeout=10) is not None
        assert other.poll() is None
        assert not procs.exists()
        assert mem.kill_leftovers(procs) == 0
    finally:
        child.kill()
        other.kill()


class FakeJob:
    def __init__(self, replies: list[tuple[int, str, int]]) -> None:
        self.replies = replies
        self.calls = 0
        self.last_pauses = 0
        self.ok = True
        self.lines: list[str] = []

    def run(self, title, cmd, step="light"):
        rc, text, pauses = self.replies[self.calls]
        self.calls += 1
        self.last_pauses = pauses
        return rc, text

    def note(self, text):
        self.lines.append(text)

    def fail(self, text):
        self.ok = False
        self.lines.append(text)


def test_paused_test_step_that_failed_runs_once_more():
    run = _load("_run")
    args = (lambda: ["x"], "pytest", run.pytest_failures, run.pytest_tally, [])
    job = FakeJob([(1, "FAILED tests/a.py::t - timeout\n1 failed, 3 passed", 1), (0, "4 passed", 0)])
    run.test_step(job, "Python", *args)
    assert job.calls == 2 and job.ok
    job = FakeJob([(1, "FAILED tests/a.py::t\n1 failed, 3 passed", 0)])
    run.test_step(job, "Python", *args)
    assert job.calls == 1 and not job.ok
    job = FakeJob([(1, "FAILED tests/a.py::t\n1 failed", 2), (1, "FAILED tests/a.py::t\n1 failed", 1)])
    run.test_step(job, "Python", *args)
    assert job.calls == 2 and not job.ok


def test_runner_restarts_a_dead_window_but_not_after_deploy():
    src = (CLICK / "_run.py").read_text(encoding="utf-8")
    body = src[src.index("    def run(") : src.index("def _decode")]
    assert body.index('if step == "ship":') < body.index("restart_ok.unlink") < body.index("subprocess.Popen(")
    assert "pausable=step in _mem.PAUSABLE" in body
    assert "except MemoryError:" in src and "return 75" in src
    main = src[src.index("def main()") :]
    assert main.index("take_lock(name)") < main.index("_mem.kill_leftovers(PROCS)")
    assert main.index("job.result.write_text(") < main.index("job.restart_ok.unlink(missing_ok=True)")
    cmd = (CLICK / "_job.cmd").read_bytes()
    text = cmd.decode("ascii")
    assert b"\r\n" in cmd
    assert ":again" in text and "goto again" in text
    assert 'findstr /b /c:"DONE" /c:"FAILED"' in text
    assert 'if not exist "click\\out\\%~2.restart_ok" goto :eof' in text
    assert "GTR 20" in text
