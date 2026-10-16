"""Run one ASR click job in this window (design/402, design/404).

usage: python click/_run.py JOB

Everything the job prints goes to click/out/JOB.log. A short Korean summary goes
to click/out/JOB.result.txt, which is the only file the agent reads afterwards.
Every step passes the memory traffic light in _mem.py before it starts.
"""

from __future__ import annotations

import ctypes
import datetime as dt
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _mem  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "click" / "out"
LOCK = OUT / ".running"
KNOWN = ROOT / "click" / "known_failures.txt"
APK = ROOT / "mobile" / "build" / "app" / "outputs" / "flutter-apk" / "app-release.apk"
PACKAGE = "com.gjtuc.sentence_reading"
STOCK_MARK = re.compile(r"lifecycle_ga|\\repos\\stock\\", re.I)

LABELS = {
    "tests": "테스트 전체",
    "ship_install": "배포하고 폰에 설치",
    "selftest": "실행기 점검",
    "web_build": "웹 빌드하고 열어 보기",
}
QUICK = {"selftest"}


class Job:
    def __init__(self, name: str, label: str) -> None:
        self.name = name
        self.label = label
        self.log = open(OUT / f"{name}.log", "w", encoding="utf-8")
        self.result = OUT / f"{name}.result.txt"
        self.lines: list[str] = []
        self.ok = True
        self.history = _mem.History(OUT / "mem_history.json")
        self.waited_min = 0.0

    def say(self, text: str = "") -> None:
        print(text, flush=True)
        self.log.write(text + "\n")
        self.log.flush()

    def note(self, text: str) -> None:
        self.lines.append(text)
        self.say(text)

    def fail(self, text: str) -> None:
        self.ok = False
        self.note(text)

    def status(self, text: str) -> None:
        self.result.write_text(f"{self.label}: {text}\n", encoding="utf-8")

    def light(self, title: str, step: str) -> None:
        if step == "none":
            return
        need = self.history.need(step)
        waited = _mem.wait_for(need, title, self.say, self.status, stock_jobs)
        self.status(f"실행 중 - {title}")
        if waited >= 1:
            self.waited_min += waited
            self.note(f"메모리 기다림: {title} 앞에서 {waited:.0f}분")

    def run(
        self, title: str, cmd: list[str], step: str = "light", env: dict[str, str] | None = None
    ) -> tuple[int, str]:
        self.light(title, step)
        self.say("")
        self.say(f"=== {title} === (남은 메모리 {_mem.free_gb():.1f}GB)")
        full_env = dict(os.environ, PYTHONUNBUFFERED="1", PYTHONIOENCODING="utf-8", PYTHONUTF8="1")
        full_env.update(env or {})
        proc = subprocess.Popen(
            cmd, cwd=ROOT, env=full_env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT
        )
        watch = _mem.Watch(proc.pid).start(
            lambda free: self.say(f"[주의] 남은 메모리 {free:.1f}GB - PC가 느려질 수 있습니다")
        )
        out: list[str] = []
        assert proc.stdout is not None
        for raw in proc.stdout:
            line = _decode(raw).rstrip("\r\n")
            out.append(line)
            self.say(line)
        rc = proc.wait()
        watch.stop()
        if watch.peak_gb > 0.05:
            self.history.record(step, watch.peak_gb)
        self.say(
            f"=== {title}: exit {rc} (가장 많이 쓴 메모리 {watch.peak_gb:.1f}GB, "
            f"가장 적게 남았을 때 {watch.min_free_gb:.1f}GB) ==="
        )
        return rc, "\n".join(out)


def _decode(raw: bytes) -> str:
    if raw[1:2] == b"\x00":
        try:
            return raw.decode("utf-16-le")
        except UnicodeDecodeError:
            pass
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode("cp949", errors="replace")


def app_version() -> str:
    text = (ROOT / "src" / "sentence_reading" / "api" / "app.py").read_text(encoding="utf-8")
    m = re.search(r'^\s*version="([0-9]+\.[0-9]+\.[0-9]+)",', text, re.M)
    if not m:
        raise SystemExit("app.py version not found")
    return m.group(1)


def known_failures() -> list[str]:
    if not KNOWN.exists():
        return []
    rows = KNOWN.read_text(encoding="utf-8").splitlines()
    return [r.strip() for r in rows if r.strip() and not r.lstrip().startswith("#")]


def split_known(failed: list[str], known: list[str]) -> tuple[list[str], list[str]]:
    old = [f for f in failed if any(k in f for k in known)]
    new = [f for f in failed if f not in old]
    return old, new


def pytest_failures(text: str) -> list[str]:
    return [m.group(1).strip() for m in re.finditer(r"^FAILED (\S+)", text, re.M)]


def pytest_tally(text: str) -> str:
    rows = re.findall(r"^=*\s*(\d+ (?:failed|passed)[^=\n]*?)\s*=*\s*$", text, re.M)
    return rows[-1] if rows else ""


def flutter_failures(text: str) -> list[str]:
    m = re.search(r"^Failing tests:\s*$(.*)", text, re.M | re.S)
    if not m:
        return []
    return [r.strip() for r in m.group(1).splitlines() if ".dart" in r]


def flutter_tally(text: str) -> str:
    rows = re.findall(r"\+(\d+)(?: ~\d+)?(?: -(\d+))?: (?:All tests passed!|Some tests failed\.)", text)
    if not rows:
        return ""
    passed, failed = rows[-1]
    return f"{passed} passed, {failed or 0} failed"


def probe_summary(text: str) -> dict[str, int]:
    rows = text.splitlines()
    uncaught = sum(1 for r in rows if r.startswith("UNCAUGHT"))
    cors = sum(1 for r in rows if r.startswith("LOG-ERROR") and "CORS policy" in r)
    other = sum(
        1 for r in rows
        if r.startswith(("LOG-ERROR", "ERROR"))
        and "CORS policy" not in r
        and "Failed to load resource" not in r
    )
    return {"uncaught": uncaught, "cors": cors, "other": other}


def stock_jobs() -> list[str]:
    """Python processes started by a stock click window. The windows stay open
    after a job ends (cmd /k), so only a live Python child counts."""
    script = (
        "$all = @{}; Get-CimInstance Win32_Process | ForEach-Object { $all[[int]$_.ProcessId] = $_ }; "
        "$all.Values | Where-Object { $_.Name -eq 'python.exe' } | ForEach-Object { "
        "$p = $all[[int]$_.ParentProcessId]; "
        "[string]$_.ProcessId + \"`t\" + $_.CommandLine + \"`t\" + $(if ($p) { $p.CommandLine } else { '' }) }"
    )
    try:
        out = subprocess.run(
            ["powershell", "-NoProfile", "-Command", script],
            capture_output=True, timeout=60,
        ).stdout
    except Exception:
        return []
    jobs = []
    for row in _decode(out).splitlines():
        parts = row.split("\t")
        if len(parts) < 3 or parts[0] == str(os.getpid()):
            continue
        own, parent = parts[1], parts[2]
        if "_tee.py" in own and STOCK_MARK.search(parent):
            m = re.search(r"runs\\logs\\([^\\\s]+)\.log", own)
            jobs.append(m.group(1) if m else own)
    return jobs


def _pid_alive(pid: int) -> bool:
    k32 = ctypes.windll.kernel32
    h = k32.OpenProcess(0x1000, False, pid)
    if not h:
        return False
    code = ctypes.c_ulong()
    k32.GetExitCodeProcess(h, ctypes.byref(code))
    k32.CloseHandle(h)
    return code.value == 259


def take_lock(name: str) -> str | None:
    if LOCK.exists():
        try:
            pid_s, other = LOCK.read_text(encoding="utf-8").split(" ", 1)
            if _pid_alive(int(pid_s)):
                return other.strip()
        except Exception:
            pass
    LOCK.write_text(f"{os.getpid()} {name}", encoding="utf-8")
    return None


def find_adb() -> str | None:
    p = Path(os.environ.get("LOCALAPPDATA", "")) / "Android" / "Sdk" / "platform-tools" / "adb.exe"
    return str(p) if p.exists() else shutil.which("adb")


def adb_devices(adb: str) -> list[str]:
    for _ in range(3):
        out = _decode(subprocess.run([adb, "devices"], capture_output=True, timeout=60).stdout)
        found = [r.split("\t")[0] for r in out.splitlines() if r.endswith("\tdevice")]
        if found:
            return found
        time.sleep(3)
    return []


def installed_version(adb: str, serial: str) -> str:
    out = _decode(
        subprocess.run(
            [adb, "-s", serial, "shell", "dumpsys", "package", PACKAGE],
            capture_output=True, timeout=60,
        ).stdout
    )
    m = re.search(r"versionName=(\S+)", out)
    return m.group(1) if m else ""


def flutter_test_args(job: Job) -> list[str]:
    job.light("Flutter 테스트", "flutter_test")
    workers = _mem.flutter_test_workers(_mem.usable_gb(), os.cpu_count() or 4)
    job.note(f"Flutter 테스트 동시 실행 {workers}개 (남은 메모리 기준)")
    return ["cmd", "/c", r"scripts\flutter_test.cmd", f"--concurrency={workers}"]


def job_tests(job: Job) -> None:
    known = known_failures()
    rc, text = job.run(
        "Python 테스트",
        ["cmd", "/c", r"scripts\pytest.cmd", "tests", "-q", "-p", "no:cacheprovider"],
        step="pytest",
    )
    failed = pytest_failures(text)
    old, new = split_known(failed, known)
    job.note(f"Python: {pytest_tally(text) or f'exit {rc}'}")
    if old:
        job.note(f"  이미 알던 실패 {len(old)}개")
    for f in new:
        job.fail(f"  새 실패: {f}")
    if rc != 0 and not failed:
        job.fail("  Python 테스트가 결과 없이 끝남. 로그를 볼 것")

    rc, text = job.run("Flutter 테스트", flutter_test_args(job), step="flutter_test")
    failed = flutter_failures(text)
    old, new = split_known(failed, known)
    job.note(f"Flutter: {flutter_tally(text) or f'exit {rc}'}")
    if old:
        job.note(f"  이미 알던 실패 {len(old)}개")
    for f in new:
        job.fail(f"  새 실패: {f}")
    if rc != 0 and not failed:
        job.fail("  Flutter 테스트가 결과 없이 끝남. 로그를 볼 것")


def build_apk(job: Job) -> tuple[int, float]:
    freed = _mem.stop_gradle_daemons()
    if freed >= 0.1:
        job.note(f"쉬고 있던 Gradle 정리: {freed:.1f}GB 돌려받음")
    job.light("앱 빌드", "apk")
    heap = _mem.apk_heap_gb(_mem.usable_gb())
    job.note(f"앱 빌드 최대 메모리 {heap:.1f}GB (원래 8GB, 남은 메모리 기준)")
    t0 = time.time()
    ps = ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File"]
    rc, _ = job.run(
        "앱 빌드",
        ps + [r"scripts\build_release_apk.ps1", "-SkipInstall"],
        step="apk",
        env={"GRADLE_OPTS": f"-Dorg.gradle.jvmargs=-Xmx{int(heap * 1024)}m"},
    )
    freed = _mem.stop_gradle_daemons()
    if freed >= 0.1:
        job.note(f"빌드 뒤 Gradle 정리: {freed:.1f}GB 돌려받음")
    return rc, t0


def job_ship_install(job: Job) -> None:
    want = app_version()
    job.note(f"배포할 버전: {want}")
    py = sys.executable
    for title, script in (
        ("최신 상태 확인", "scripts/session_freshness_guard.py"),
        ("증거 바닥 확인", "scripts/check_evidence_floor.py"),
        ("배포 전 점검", "scripts/pre_deploy_guard.py"),
    ):
        rc, text = job.run(title, [py, script])
        if rc != 0:
            errs = re.findall(r'"errors": \[([^\]]*)\]', text)
            job.fail(f"{title} 실패 (exit {rc}). 배포하지 않음. {errs[-1] if errs else ''}".rstrip())
            return
    job.note("배포 전 점검 통과")

    ps = ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File"]
    rc, text = job.run("서버 배포", ps + [r"scripts\ship_cloud_pair.ps1"], step="ship")
    shipped = "ship_release OK" in text
    job.note("서버 배포: ship_release OK" if shipped else f"서버 배포: ship_release OK 없음 (exit {rc}). 서버 버전만 확인함")

    rc, text = job.run(
        "서버 버전 확인",
        [py, "scripts/verify_live_status.py", "--require-azure-layout", "--min-pipeline", "rich-v20", "--expect", want],
    )
    if rc != 0:
        job.fail(f"서버 버전 확인 실패 (exit {rc}). 앱은 빌드하지 않음")
        return
    job.note(f"서버 버전 확인: {want} live")

    rc, t0 = build_apk(job)
    if not APK.exists() or APK.stat().st_mtime < t0:
        job.fail(f"앱 빌드 실패 (exit {rc}). 새 APK 없음")
        return
    job.note("앱 빌드: 새 APK 만듦")

    adb = find_adb()
    if not adb:
        job.fail("adb 를 찾지 못해 설치 못 함")
        return
    devices = adb_devices(adb)
    if len(devices) != 1:
        job.fail(f"연결된 폰 {len(devices)}대. 설치 안 함 (한 대만 연결할 것)")
        return
    job.run("폰 설치", [adb, "-s", devices[0], "install", "-r", str(APK)])
    got = installed_version(adb, devices[0])
    if got != want:
        job.fail(f"폰 설치 확인 실패: 폰 버전 {got or '없음'}, 기대 {want}")
        return
    job.note(f"폰 설치: versionName {got}")


def job_web_build(job: Job) -> None:
    rc, _ = job.run(
        "웹 빌드",
        ["cmd", "/c", r"scripts\flutter_any.cmd", "build", "web", "--release", "--no-wasm-dry-run"],
        step="web_build",
    )
    if rc != 0:
        job.fail(f"웹 빌드 실패 (exit {rc})")
        return
    job.note("웹 빌드: mobile/build/web")
    out = ROOT / ".cache" / "web_probe"
    rc, _ = job.run(
        "웹 화면 열어 보기", [sys.executable, "scripts/web_probe.py", "--out", str(out)], step="probe"
    )
    console = Path(str(out) + ".console.txt")
    if rc != 0 or not console.exists():
        job.fail(f"웹 화면 열기 실패 (exit {rc})")
        return
    s = probe_summary(console.read_text(encoding="utf-8"))
    job.note(f"잡히지 않은 오류 {s['uncaught']}개, 다른 오류 {s['other']}개")
    job.note(f"서버 주소가 달라 막힌 요청(CORS) {s['cors']}개 - 이 PC에서 열 때만 생김")
    job.note("화면: .cache/web_probe.png  콘솔: .cache/web_probe.console.txt")
    if s["uncaught"] or s["other"]:
        job.fail("웹 화면에 오류가 있음. 콘솔 파일을 볼 것")


def job_selftest(job: Job) -> None:
    rc, text = job.run("파이썬 확인", [sys.executable, "--version"], step="none")
    job.note(f"파이썬: {text.strip()}" if rc == 0 else f"파이썬 확인 실패 (exit {rc})")
    job.note(f"앱 버전: {app_version()}")
    job.note(f"주식 작업: {', '.join(stock_jobs()) or '없음'}")
    usable = _mem.usable_gb()
    job.note(f"지금 쓸 수 있는 메모리 {usable:.1f}GB (PC 몫 {_mem.RESERVE_GB:.0f}GB 뺀 값)")
    job.note(
        f"지금 시작하면: Flutter 테스트 동시 {_mem.flutter_test_workers(usable, os.cpu_count() or 4)}개, "
        f"앱 빌드 최대 {_mem.apk_heap_gb(usable):.1f}GB"
    )
    waits = [
        f"{step} {job.history.need(step):.1f}GB"
        for step in ("pytest", "flutter_test", "web_build", "apk", "ship")
        if job.history.need(step) > usable
    ]
    job.note("지금 시작하면 기다릴 단계: " + (", ".join(waits) if waits else "없음"))


JOBS = {
    "tests": job_tests,
    "ship_install": job_ship_install,
    "selftest": job_selftest,
    "web_build": job_web_build,
}


def main() -> int:
    name = sys.argv[1] if len(sys.argv) > 1 else ""
    if name not in JOBS:
        print(f"unknown job: {name}. choose one of {', '.join(JOBS)}")
        return 2
    label = LABELS[name]
    OUT.mkdir(parents=True, exist_ok=True)
    ctypes.windll.kernel32.SetConsoleTitleW(f"문장읽기 - {label}")

    other = take_lock(name)
    if other:
        print(f"문장읽기 작업 '{other}' 이 이미 실행 중입니다. 끝난 뒤 다시 실행하세요.")
        return 3

    try:
        job = Job(name, label)
        started = dt.datetime.now()
        job.status(f"실행 중 ({started:%Y-%m-%d %H:%M})")
        job.say(f"문장읽기 - {label}")
        job.say(f"시작 {started:%Y-%m-%d %H:%M:%S}  기록 {job.log.name}")
        if name not in QUICK:
            stock = stock_jobs()
            if stock:
                job.say(f"주식 작업이 실행 중입니다: {', '.join(stock)}. 메모리가 빌 때만 단계를 시작합니다.")
        try:
            JOBS[name](job)
        except Exception as e:
            job.fail(f"작업 중 오류: {type(e).__name__}: {e}")
        ended = dt.datetime.now()
        minutes = (ended - started).total_seconds() / 60
        head = "DONE" if job.ok else "FAILED"
        body = [
            f"{head} - {label}",
            f"시작 {started:%Y-%m-%d %H:%M}  끝 {ended:%H:%M}  ({minutes:.0f}분"
            + (f", 그중 메모리 기다림 {job.waited_min:.0f}분)" if job.waited_min >= 1 else ")"),
            *job.lines,
            f"전체 기록: click/out/{name}.log",
        ]
        job.result.write_text("\n".join(body) + "\n", encoding="utf-8")
        job.say("")
        job.say("=" * 50)
        for row in body:
            job.say(row)
        job.say("=" * 50)
        job.say("창을 닫아도 됩니다.")
        job.log.close()
        try:
            import winsound

            for _ in range(3):
                winsound.MessageBeep(winsound.MB_ICONASTERISK if job.ok else winsound.MB_ICONHAND)
                time.sleep(0.4)
        except Exception:
            pass
        return 0 if job.ok else 1
    finally:
        try:
            if LOCK.read_text(encoding="utf-8").startswith(f"{os.getpid()} "):
                LOCK.unlink()
        except Exception:
            pass


if __name__ == "__main__":
    sys.exit(main())
