"""design/404 - memory traffic light for click jobs.

Every step declares what it needs. Before the step starts, the light waits until
that much memory is free on top of a reserve for the desktop. Steps with a knob
(Flutter test concurrency, Gradle heap) are sized to what is free when they start.
Each step's measured peak is kept so the next run asks for what it really used.

design/406 - the light keeps watching while a step runs. When free memory drops
below the reserve and a stock job is running, the step's processes are suspended
(red) and resumed once memory is back (green), as often as needed. Suspending
does not hand memory back; it stops the step from taking more while the stock
job needs it.
"""

from __future__ import annotations

import ctypes
import json
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

import psutil

GB = 1024**3
RESERVE_GB = 1.0
POLL_S = 15
SAY_EVERY_S = 300
MAX_WAIT_S = 8 * 3600
HISTORY_KEEP = 5
LOW_FREE_GB = 0.4
# Mid-step: red below PAUSE_BELOW_GB usable, green again at RESUME_AT_GB.
PAUSE_BELOW_GB = 0.0
RESUME_AT_GB = 0.5
WATCH_S = 2
OTHERS_EVERY_S = 60
# Deploy, phone install and the browser check run on wall-clock timeouts.
PAUSABLE = {"pytest", "flutter_test", "web_build", "apk"}

# Smallest amount each step can run with. Learned peaks raise it for fixed steps.
MIN_NEED_GB = {
    "light": 0.3,
    "ship": 1.0,
    "pytest": 1.5,
    "flutter_test": 1.2,
    "web_build": 2.5,
    # 0.3.444 build peaked at 2.6 GB with a 2.5 GB heap.
    "apk": 3.0,
    "probe": 0.8,
}
# Steps whose size is set by a knob; their history is reported, not gated on.
SCALED = {"flutter_test", "apk"}
FLUTTER_TEST_GB_PER_WORKER = 0.6
APK_OTHER_GB = 1.5
APK_HEAP_MIN_GB = 2.0
APK_HEAP_MAX_GB = 8.0


class _MemStatus(ctypes.Structure):
    _fields_ = [
        ("dwLength", ctypes.c_ulong),
        ("dwMemoryLoad", ctypes.c_ulong),
        ("ullTotalPhys", ctypes.c_ulonglong),
        ("ullAvailPhys", ctypes.c_ulonglong),
        ("ullTotalPageFile", ctypes.c_ulonglong),
        ("ullAvailPageFile", ctypes.c_ulonglong),
        ("ullTotalVirtual", ctypes.c_ulonglong),
        ("ullAvailVirtual", ctypes.c_ulonglong),
        ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
    ]


def free_gb() -> float:
    """Usable memory now: the smaller of free RAM and free commit (page file)."""
    st = _MemStatus()
    st.dwLength = ctypes.sizeof(_MemStatus)
    ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(st))
    return min(st.ullAvailPhys, st.ullAvailPageFile) / GB


def usable_gb(free: float | None = None) -> float:
    return (free_gb() if free is None else free) - RESERVE_GB


def flutter_test_workers(usable: float, cores: int) -> int:
    return max(1, min(cores, int(usable / FLUTTER_TEST_GB_PER_WORKER)))


def apk_heap_gb(usable: float) -> float:
    heap = usable - APK_OTHER_GB
    heap = max(APK_HEAP_MIN_GB, min(APK_HEAP_MAX_GB, heap))
    return int(heap * 2) / 2


class History:
    def __init__(self, path: Path) -> None:
        self.path = path
        try:
            self.data: dict[str, list[float]] = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            self.data = {}

    def need(self, step: str) -> float:
        floor = MIN_NEED_GB.get(step, MIN_NEED_GB["light"])
        peaks = self.data.get(step) or []
        if step in SCALED or not peaks:
            return floor
        return max(floor, round(max(peaks) * 1.2, 1))

    def record(self, step: str, peak_gb: float) -> None:
        rows = (self.data.get(step) or []) + [round(peak_gb, 2)]
        self.data[step] = rows[-HISTORY_KEEP:]
        try:
            self.path.write_text(json.dumps(self.data, indent=1), encoding="utf-8")
        except Exception:
            pass


def wait_for(need: float, title: str, say, status, others) -> float:
    """Block until `need` GB is usable. Returns minutes waited."""
    t0 = time.time()
    last_say = 0.0
    while True:
        try:
            usable = usable_gb()
        except MemoryError:
            time.sleep(POLL_S)
            continue
        if usable >= need:
            return (time.time() - t0) / 60
        waited = time.time() - t0
        if waited > MAX_WAIT_S:
            raise TimeoutError(f"{title}: {MAX_WAIT_S // 3600}시간 기다려도 메모리가 비지 않음")
        if time.time() - last_say >= SAY_EVERY_S or last_say == 0.0:
            busy = others()
            tail = f" (주식 작업: {', '.join(busy)})" if busy else ""
            say(
                f"[빨간불] {title}: 필요 {need:.1f}GB, 지금 쓸 수 있는 {max(usable, 0):.1f}GB. "
                f"{POLL_S}초마다 다시 봅니다{tail}"
            )
            status(f"메모리 기다리는 중: {title} 앞 ({waited / 60:.0f}분째)")
            last_say = time.time()
        time.sleep(POLL_S)


@dataclass
class Watch:
    """Samples the step's process tree and the machine while the step runs.

    With `pausable`, a red light suspends the tree (plus `extra()` processes such
    as Gradle daemons that are not its children) and a green light resumes it.
    The live tree is written to `procs_file` so a later run can clean up after a
    window that died."""

    pid: int
    pausable: bool = False
    extra: Callable[[], list[psutil.Process]] | None = None
    procs_file: Path | None = None
    peak_gb: float = 0.0
    min_free_gb: float = field(default=99.0)
    pauses: int = 0
    paused_s: float = 0.0
    _held: dict[int, psutil.Process] = field(default_factory=dict)
    _paused_at: float | None = None
    _others_at: float = 0.0
    _others: list[str] = field(default_factory=list)
    _saved: str = ""
    _stop: threading.Event = field(default_factory=threading.Event)
    _thread: threading.Thread | None = None

    def tree(self) -> list[psutil.Process]:
        try:
            root = psutil.Process(self.pid)
            procs = [root, *root.children(recursive=True)]
        except psutil.Error:
            procs = []
        if self.extra:
            seen = {p.pid for p in procs}
            procs += [p for p in self.extra() if p.pid not in seen]
        return procs

    def gate(self, usable: float, procs: list[psutil.Process], others: Callable[[], list[str]]) -> str:
        """One look at the light. Returns "pause", "resume" or ""."""
        if not self.pausable:
            return ""
        now = time.time()
        if self._paused_at is None:
            if usable >= PAUSE_BELOW_GB or not self._stock(others, now):
                return ""
            self._hold(procs)
            self._paused_at = now
            self.pauses += 1
            return "pause"
        if usable >= RESUME_AT_GB or not self._stock(others, now):
            self.release()
            return "resume"
        self._hold(procs)
        return ""

    def _stock(self, others: Callable[[], list[str]], now: float) -> list[str]:
        # Nobody else will free memory when no stock job runs; pausing would never end.
        if now - self._others_at >= OTHERS_EVERY_S or self._others_at == 0.0:
            try:
                self._others = list(others())
            except Exception:
                self._others = []
            self._others_at = now
        return self._others

    def _hold(self, procs: list[psutil.Process]) -> None:
        for p in procs:
            if p.pid in self._held:
                continue
            try:
                p.suspend()
                self._held[p.pid] = p
            except psutil.Error:
                pass

    def release(self) -> None:
        for p in self._held.values():
            try:
                p.resume()
            except psutil.Error:
                pass
        self._held.clear()
        if self._paused_at is not None:
            self.paused_s += time.time() - self._paused_at
            self._paused_at = None

    @property
    def paused(self) -> bool:
        return self._paused_at is not None

    def save(self, procs: list[psutil.Process]) -> None:
        if self.procs_file is None:
            return
        rows = []
        for p in procs:
            try:
                rows.append(f"{p.pid} {p.create_time():.3f}")
            except psutil.Error:
                pass
        text = "\n".join(sorted(rows))
        if text != self._saved:
            try:
                self.procs_file.write_text(text, encoding="utf-8")
                self._saved = text
            except OSError:
                pass

    def start(self, on_low, on_pause=None, on_resume=None, others=lambda: []) -> "Watch":
        def loop() -> None:
            warned = False
            while not self._stop.wait(WATCH_S):
                try:
                    procs = self.tree()
                    rss = 0
                    for p in procs:
                        try:
                            rss += p.memory_info().rss
                        except psutil.Error:
                            pass
                    self.peak_gb = max(self.peak_gb, rss / GB)
                    self.save(procs)
                    free = free_gb()
                    self.min_free_gb = min(self.min_free_gb, free)
                    if free < LOW_FREE_GB and not warned and not self.pausable:
                        on_low(free)
                        warned = True
                    since = self._paused_at
                    turn = self.gate(free - RESERVE_GB, procs, others)
                    if turn == "pause" and on_pause:
                        on_pause(free - RESERVE_GB, self._others)
                    elif turn == "resume" and on_resume:
                        on_resume(free - RESERVE_GB, time.time() - (since or time.time()))
                except Exception:
                    pass

        self._thread = threading.Thread(target=loop, daemon=True)
        self._thread.start()
        return self

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=10)
        self.release()
        if self.procs_file is not None:
            try:
                self.procs_file.unlink()
            except OSError:
                pass


def kill_leftovers(procs_file: Path) -> int:
    """Kill processes a dead window's step left behind (suspended ones included)."""
    try:
        rows = procs_file.read_text(encoding="utf-8").split()
    except OSError:
        return 0
    killed = 0
    for pid_s, ctime_s in zip(rows[::2], rows[1::2]):
        try:
            p = psutil.Process(int(pid_s))
            if abs(p.create_time() - float(ctime_s)) > 1:
                continue
            p.kill()
            killed += 1
        except (psutil.Error, ValueError):
            pass
    try:
        procs_file.unlink()
    except OSError:
        pass
    return killed


def build_daemons() -> list[psutil.Process]:
    """Gradle and Kotlin daemons run detached from the build's process tree."""
    found = []
    for p in psutil.process_iter(["name", "cmdline"]):
        try:
            if (p.info["name"] or "").lower() == "java.exe" and any(
                "GradleDaemon" in c or "KotlinCompileDaemon" in c for c in (p.info["cmdline"] or [])
            ):
                found.append(p)
        except psutil.Error:
            pass
    return found


def gradle_daemons() -> list[psutil.Process]:
    found = []
    for p in psutil.process_iter(["name", "cmdline"]):
        try:
            if (p.info["name"] or "").lower() == "java.exe" and any(
                "GradleDaemon" in c for c in (p.info["cmdline"] or [])
            ):
                found.append(p)
        except psutil.Error:
            pass
    return found


def stop_gradle_daemons() -> float:
    """Idle Gradle daemons hold their heap for hours. Returns GB released."""
    freed = 0.0
    for p in gradle_daemons():
        try:
            freed += p.memory_info().rss / GB
            p.kill()
        except psutil.Error:
            pass
    return freed
