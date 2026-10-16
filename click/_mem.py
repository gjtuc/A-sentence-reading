"""design/404 - memory traffic light for click jobs.

Every step declares what it needs. Before the step starts, the light waits until
that much memory is free on top of a reserve for the desktop. Steps with a knob
(Flutter test concurrency, Gradle heap) are sized to what is free when they start.
Each step's measured peak is kept so the next run asks for what it really used.
"""

from __future__ import annotations

import ctypes
import json
import threading
import time
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

# Smallest amount each step can run with. Learned peaks raise it for fixed steps.
MIN_NEED_GB = {
    "light": 0.3,
    "ship": 1.0,
    "pytest": 1.5,
    "flutter_test": 1.2,
    "web_build": 2.5,
    "apk": 3.5,
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
        usable = usable_gb()
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
    """Samples the step's process tree and the machine while the step runs."""

    pid: int
    peak_gb: float = 0.0
    min_free_gb: float = field(default=99.0)
    _stop: threading.Event = field(default_factory=threading.Event)
    _thread: threading.Thread | None = None

    def start(self, on_low) -> "Watch":
        def loop() -> None:
            warned = False
            while not self._stop.wait(2):
                try:
                    root = psutil.Process(self.pid)
                    procs = [root, *root.children(recursive=True)]
                    rss = 0
                    for p in procs:
                        try:
                            rss += p.memory_info().rss
                        except psutil.Error:
                            pass
                    self.peak_gb = max(self.peak_gb, rss / GB)
                except psutil.Error:
                    pass
                free = free_gb()
                self.min_free_gb = min(self.min_free_gb, free)
                if free < LOW_FREE_GB and not warned:
                    on_low(free)
                    warned = True

        self._thread = threading.Thread(target=loop, daemon=True)
        self._thread.start()
        return self

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=5)


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
