"""Run one ASR click job in this window (design/402).

usage: python click/_run.py JOB

Everything the job prints goes to click/out/JOB.log. A short Korean summary goes
to click/out/JOB.result.txt, which is the only file the agent reads afterwards.
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

ROOT = Path(__file__).resolve().parent.parent
LOGS = ROOT / "click" / "out"
LOCK = LOGS / ".running"
KNOWN = ROOT / "click" / "known_failures.txt"
APK = ROOT / "mobile" / "build" / "app" / "outputs" / "flutter-apk" / "app-release.apk"
PACKAGE = "com.gjtuc.sentence_reading"
STOCK_MARK = re.compile(r"lifecycle_ga|\\repos\\stock\\", re.I)

LABELS = {
    "tests": "테스트 전체",
    "ship_install": "배포하고 폰에 설치",
    "selftest": "실행기 점검",
}
QUICK = {"selftest"}


class Job:
    def __init__(self, name: str) -> None:
        self.name = name
        self.log = open(LOGS / f"{name}.log", "w", encoding="utf-8")
        self.lines: list[str] = []
        self.ok = True

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

    def run(self, title: str, cmd: list[str]) -> tuple[int, str]:
        self.say("")
        self.say(f"=== {title} ===")
        env = dict(os.environ, PYTHONUNBUFFERED="1", PYTHONIOENCODING="utf-8", PYTHONUTF8="1")
        proc = subprocess.Popen(
            cmd, cwd=ROOT, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT
        )
        out: list[str] = []
        assert proc.stdout is not None
        for raw in proc.stdout:
            line = _decode(raw).rstrip("\r\n")
            out.append(line)
            self.say(line)
        rc = proc.wait()
        self.say(f"=== {title}: exit {rc} ===")
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


def job_tests(job: Job) -> None:
    known = known_failures()
    rc, text = job.run("Python 테스트", ["cmd", "/c", r"scripts\pytest.cmd", "tests", "-q", "-p", "no:cacheprovider"])
    failed = pytest_failures(text)
    old, new = split_known(failed, known)
    job.note(f"Python: {pytest_tally(text) or f'exit {rc}'}")
    if old:
        job.note(f"  이미 알던 실패 {len(old)}개")
    for f in new:
        job.fail(f"  새 실패: {f}")
    if rc != 0 and not failed:
        job.fail("  Python 테스트가 결과 없이 끝남. 로그를 볼 것")

    rc, text = job.run("Flutter 테스트", ["cmd", "/c", r"scripts\flutter_test.cmd"])
    failed = flutter_failures(text)
    old, new = split_known(failed, known)
    job.note(f"Flutter: {flutter_tally(text) or f'exit {rc}'}")
    if old:
        job.note(f"  이미 알던 실패 {len(old)}개")
    for f in new:
        job.fail(f"  새 실패: {f}")
    if rc != 0 and not failed:
        job.fail("  Flutter 테스트가 결과 없이 끝남. 로그를 볼 것")


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
    rc, text = job.run("서버 배포", ps + [r"scripts\ship_cloud_pair.ps1"])
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

    t0 = time.time()
    rc, text = job.run("앱 빌드", ps + [r"scripts\build_release_apk.ps1", "-SkipInstall"])
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
    rc, _ = job.run("폰 설치", [adb, "-s", devices[0], "install", "-r", str(APK)])
    got = installed_version(adb, devices[0])
    if got != want:
        job.fail(f"폰 설치 확인 실패: 폰 버전 {got or '없음'}, 기대 {want}")
        return
    job.note(f"폰 설치: versionName {got}")


def job_selftest(job: Job) -> None:
    rc, text = job.run("파이썬 확인", [sys.executable, "--version"])
    job.note(f"파이썬: {text.strip()}" if rc == 0 else f"파이썬 확인 실패 (exit {rc})")
    job.note(f"앱 버전: {app_version()}")
    job.note(f"주식 작업: {', '.join(stock_jobs()) or '없음'}")


JOBS = {"tests": job_tests, "ship_install": job_ship_install, "selftest": job_selftest}


def main() -> int:
    name = sys.argv[1] if len(sys.argv) > 1 else ""
    if name not in JOBS:
        print(f"unknown job: {name}. choose one of {', '.join(JOBS)}")
        return 2
    label = LABELS[name]
    LOGS.mkdir(parents=True, exist_ok=True)
    ctypes.windll.kernel32.SetConsoleTitleW(f"문장읽기 - {label}")
    result = LOGS / f"{name}.result.txt"

    other = take_lock(name)
    if other:
        print(f"문장읽기 작업 '{other}' 이 이미 실행 중입니다. 끝난 뒤 다시 실행하세요.")
        return 3

    try:
        stock = [] if name in QUICK else stock_jobs()
        if stock:
            print(f"주식 작업이 실행 중입니다: {', '.join(stock)}. 같이 돌리면 둘 다 느려집니다.")
            if input("그래도 계속할까요? (y/n) ").strip().lower() != "y":
                return 4

        job = Job(name)
        started = dt.datetime.now()
        result.write_text(f"{label}: 실행 중 ({started:%Y-%m-%d %H:%M})\n", encoding="utf-8")
        job.say(f"문장읽기 - {label}")
        job.say(f"시작 {started:%Y-%m-%d %H:%M:%S}  기록 {job.log.name}")
        try:
            JOBS[name](job)
        except Exception as e:
            job.fail(f"작업 중 오류: {type(e).__name__}: {e}")
        ended = dt.datetime.now()
        minutes = (ended - started).total_seconds() / 60
        head = "DONE" if job.ok else "FAILED"
        body = [
            f"{head} - {label}",
            f"시작 {started:%Y-%m-%d %H:%M}  끝 {ended:%H:%M}  ({minutes:.0f}분)",
            *job.lines,
            f"전체 기록: click/out/{name}.log",
        ]
        result.write_text("\n".join(body) + "\n", encoding="utf-8")
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
