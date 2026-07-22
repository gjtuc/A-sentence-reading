"""
무엇을: Windows 로그인/잠금해제/절전재개 시 로컬 서버 보장.
왜: pip 설치물만으로도 작업 스케줄러에 붙어, Cursor 없이도 다시 뜬다.
다음에: macOS launchd / Linux systemd user unit.

Scheduled task runs: ``{venv pythonw} -m sentence_reading.autostart ensure``
(콘솔 창 없음 · 브라우저도 안 염).
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from xml.sax.saxutils import escape

from sentence_reading.cache.paper_cache import project_root

TASK_NAME = "A-sentence-reading Ensure Server"
HOST = "127.0.0.1"
PORT = 8770
STATUS_URL = f"http://{HOST}:{PORT}/api/status"
# WHY: 절전 직후 스택이 덜 올라온 뒤 한 번 더 시도할 여유.
RESUME_DELAY = "PT10S"
# WHY: cold import of api.app alone ~18s on this PC; 2s wait falsely failed ensure.
HEALTH_WAIT_SEC = 60
HEALTH_INTERVAL_SEC = 1.0


def _log_dir() -> Path:
    return project_root() / "logs"


def _log(message: str) -> None:
    log_dir = _log_dir()
    log_dir.mkdir(parents=True, exist_ok=True)
    line = f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} {message}"
    with (log_dir / "autostart.log").open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")


def resolve_python(*, prefer_pythonw: bool = True) -> Path:
    """스케줄러용 인터프리터 — pythonw면 ensure 자체도 창이 안 뜬다."""
    exe = Path(sys.executable).resolve()
    if prefer_pythonw and exe.name.lower() == "python.exe":
        pyw = exe.with_name("pythonw.exe")
        if pyw.is_file():
            return pyw
    return exe


def _console_python(exe: Path | None = None) -> Path:
    """장수 uvicorn용 — pythonw면 python.exe로 되돌린다 (로그·자식 안정)."""
    py = Path(exe or sys.executable).resolve()
    if py.name.lower() == "pythonw.exe":
        console = py.with_name("python.exe")
        if console.is_file():
            return console
    return py


def _subprocess_flags() -> int:
    if sys.platform == "win32":
        # WHY: ensure가 python.exe로 돌더라도 uvicorn 자식 창은 안 띄운다.
        return getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
    return 0


def server_up(*, timeout: float = 2.0) -> bool:
    try:
        with urllib.request.urlopen(STATUS_URL, timeout=timeout) as resp:
            return 200 <= getattr(resp, "status", 200) < 300
    except (urllib.error.URLError, TimeoutError, OSError):
        return False


def ensure_server() -> int:
    """서버가 없으면 현재 인터프리터로 uvicorn를 백그라운드 기동."""
    if server_up():
        _log("OK: server already running")
        return 0

    root = project_root()
    log_dir = _log_dir()
    log_dir.mkdir(parents=True, exist_ok=True)
    stdout = log_dir / "uvicorn.out.log"
    stderr = log_dir / "uvicorn.err.log"
    py = _console_python()

    _log(f"START: launching uvicorn via {py}")
    # WHY: `with`로 바로 닫으면 Windows에서 자식 리다이렉트가 비거나 깨질 수 있다.
    # 핸들은 ensure 프로세스가 끝날 때까지 유지 (자식은 복제본을 가짐).
    out = stdout.open("a", encoding="utf-8")  # noqa: SIM115
    err = stderr.open("a", encoding="utf-8")  # noqa: SIM115
    try:
        popen_kwargs: dict = {
            "cwd": str(root),
            "stdout": out,
            "stderr": err,
        }
        if sys.platform == "win32":
            popen_kwargs["creationflags"] = _subprocess_flags()
            popen_kwargs["close_fds"] = False
        else:
            popen_kwargs["start_new_session"] = True
            popen_kwargs["close_fds"] = True

        subprocess.Popen(
            [
                str(py),
                "-m",
                "uvicorn",
                "sentence_reading.api.app:app",
                "--host",
                HOST,
                "--port",
                str(PORT),
            ],
            **popen_kwargs,
        )
    except OSError as exc:
        out.close()
        err.close()
        _log(f"FAIL: spawn {exc}")
        return 1

    deadline = time.time() + HEALTH_WAIT_SEC
    while time.time() < deadline:
        if server_up():
            _log("OK: server started")
            return 0
        time.sleep(HEALTH_INTERVAL_SEC)

    _log(f"FAIL: server did not become ready within {HEALTH_WAIT_SEC}s")
    return 1


def _user_id() -> str:
    domain = os.environ.get("USERDOMAIN", "")
    user = os.environ.get("USERNAME") or os.environ.get("USER", "")
    if domain and user:
        return f"{domain}\\{user}"
    return user


def _task_xml(python_exe: Path, root: Path) -> str:
    user_id = escape(_user_id())
    py = escape(str(python_exe))
    work = escape(str(root))
    query = escape(
        "<QueryList><Query Id=\"0\" Path=\"System\">"
        "<Select Path=\"System\">"
        "*[System[Provider[@Name='Microsoft-Windows-Power-Troubleshooter'] "
        "and (EventID=1)]]"
        "</Select></Query></QueryList>"
    )
    args = escape("-m sentence_reading.autostart ensure")
    return f"""<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.4" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo>
    <Description>Start A-sentence-reading local server if it is not already up (login / unlock / resume). No console window.</Description>
  </RegistrationInfo>
  <Triggers>
    <LogonTrigger>
      <Enabled>true</Enabled>
      <UserId>{user_id}</UserId>
    </LogonTrigger>
    <SessionStateChangeTrigger>
      <Enabled>true</Enabled>
      <StateChange>SessionUnlock</StateChange>
      <UserId>{user_id}</UserId>
    </SessionStateChangeTrigger>
    <EventTrigger>
      <Enabled>true</Enabled>
      <Subscription>{query}</Subscription>
      <Delay>{RESUME_DELAY}</Delay>
    </EventTrigger>
  </Triggers>
  <Principals>
    <Principal id="Author">
      <UserId>{user_id}</UserId>
      <LogonType>InteractiveToken</LogonType>
      <RunLevel>LeastPrivilege</RunLevel>
    </Principal>
  </Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <AllowHardTerminate>true</AllowHardTerminate>
    <StartWhenAvailable>true</StartWhenAvailable>
    <RunOnlyIfNetworkAvailable>false</RunOnlyIfNetworkAvailable>
    <AllowStartOnDemand>true</AllowStartOnDemand>
    <Enabled>true</Enabled>
    <Hidden>true</Hidden>
    <ExecutionTimeLimit>PT5M</ExecutionTimeLimit>
    <Priority>7</Priority>
  </Settings>
  <Actions Context="Author">
    <Exec>
      <Command>{py}</Command>
      <Arguments>{args}</Arguments>
      <WorkingDirectory>{work}</WorkingDirectory>
    </Exec>
  </Actions>
</Task>
"""


def task_registered() -> bool:
    if sys.platform != "win32":
        return False
    proc = subprocess.run(
        ["schtasks", "/Query", "/TN", TASK_NAME],
        capture_output=True,
        text=True,
        check=False,
    )
    return proc.returncode == 0


def register_task(*, quiet: bool = False) -> int:
    """pythonw로 ensure를 돌리는 작업 스케줄러 작업을 등록한다 (창 없음)."""
    if sys.platform != "win32":
        if not quiet:
            print("autostart: Windows only — skipped", file=sys.stderr)
        return 0

    root = project_root()
    python_exe = resolve_python(prefer_pythonw=True)
    xml_path = Path(os.environ.get("TEMP", str(root))) / "a-sentence-reading-autostart-task.xml"
    xml_path.write_text(_task_xml(python_exe, root), encoding="utf-16")

    subprocess.run(
        ["schtasks", "/Delete", "/TN", TASK_NAME, "/F"],
        capture_output=True,
        text=True,
        check=False,
    )
    # WHY: 예전 PS1 분리 등록 이름 정리.
    subprocess.run(
        ["schtasks", "/Delete", "/TN", "A-sentence-reading Ensure Server On Resume", "/F"],
        capture_output=True,
        text=True,
        check=False,
    )

    created = subprocess.run(
        ["schtasks", "/Create", "/TN", TASK_NAME, "/XML", str(xml_path), "/F"],
        capture_output=True,
        text=True,
        check=False,
    )
    try:
        xml_path.unlink(missing_ok=True)
    except OSError:
        pass

    if created.returncode != 0:
        msg = (created.stderr or created.stdout or "schtasks failed").strip()
        _log(f"FAIL: register — {msg}")
        if not quiet:
            print(f"autostart register failed: {msg}", file=sys.stderr)
        return 1

    _log(f"OK: registered {TASK_NAME} -> {python_exe}")
    if not quiet:
        print(f"Registered: {TASK_NAME}")
        print(f"  Python: {python_exe}")
        print(f"  Root:   {root}")
    return 0


def ensure_registered(*, quiet: bool = True) -> None:
    """이미 있으면 통과, 없으면 등록 (서버 기동 훅용)."""
    if sys.platform != "win32":
        return
    if task_registered():
        return
    register_task(quiet=quiet)


def unregister_task(*, quiet: bool = False) -> int:
    if sys.platform != "win32":
        return 0
    proc = subprocess.run(
        ["schtasks", "/Delete", "/TN", TASK_NAME, "/F"],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0 and not quiet:
        print((proc.stderr or proc.stdout or "not found").strip())
    elif not quiet:
        print(f"Unregistered: {TASK_NAME}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="sentence-reading-autostart")
    parser.add_argument(
        "command",
        nargs="?",
        default="register",
        choices=("register", "ensure", "unregister", "status"),
        help="register=스케줄러 등록(기본), ensure=서버 보장, unregister, status",
    )
    args = parser.parse_args(argv)

    if args.command == "register":
        return register_task()
    if args.command == "ensure":
        return ensure_server()
    if args.command == "unregister":
        return unregister_task()
    # status
    up = server_up()
    registered = task_registered()
    print(f"server_up={up} task_registered={registered} root={project_root()}")
    return 0 if up else 1


def entrypoint() -> None:
    raise SystemExit(main())


if __name__ == "__main__":
    entrypoint()
