# -*- coding: utf-8 -*-
"""design/495 — 논문 전송 도우미: one Windows file, no Python needed.

Built into SentenceReadingHelper.exe (scripts/build_helper_exe.py).

- Double-clicked from anywhere (Downloads): copies itself to
  %LOCALAPPDATA%\\SentenceReading\\helper, starts with Windows (HKCU Run), shows in
  Settings > Apps (HKCU Uninstall), starts the installed copy and says so.
- The installed copy runs the helper (usb_sync_bridge.serve with the paper
  store). When this PC has no adb it fetches Google's platform-tools once.
- `--uninstall` (Settings > Apps) stops it and removes the program. The paper
  copies stay where they are.
"""
from __future__ import annotations

import asyncio
import os
import shutil
import socket
import subprocess
import sys
import threading
import time
import urllib.request
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import helper_store  # noqa: E402
import usb_sync_bridge as bridge_mod  # noqa: E402

APP_NAME = "SentenceReadingHelper"
DISPLAY_NAME = "논문 전송 도우미 (문장 읽기)"
ADB_ZIP_URL = "https://dl.google.com/android/repository/platform-tools-latest-windows.zip"
ADB_FILES = ("adb.exe", "AdbWinApi.dll", "AdbWinUsbApi.dll")
ADB_RETRY_S = 600.0
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
UNINSTALL_KEY = RUN_KEY.rsplit("\\", 1)[0] + "\\Uninstall\\" + APP_NAME
LOG_MAX = 1024 * 1024


def install_dir() -> Path:
    base = os.environ.get("LOCALAPPDATA") or str(Path.home())
    return Path(base) / "SentenceReading" / "helper"


def installed_exe() -> Path:
    return install_dir() / f"{APP_NAME}.exe"


def make_log(path: Path | None = None):
    path = path or install_dir() / "helper.log"

    def log(*parts) -> None:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            if path.exists() and path.stat().st_size > LOG_MAX:
                path.write_text("", encoding="utf-8")
            with path.open("a", encoding="utf-8") as fh:
                fh.write(time.strftime("%Y-%m-%d %H:%M:%S ") + " ".join(str(p) for p in parts) + "\n")
        except OSError:
            pass

    return log


def message(text: str, *, error: bool = False) -> None:
    try:
        import ctypes

        ctypes.windll.user32.MessageBoxW(0, text, DISPLAY_NAME, 0x10 if error else 0x40)
    except Exception:
        pass


def port_busy(port: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=1):
            return True
    except OSError:
        return False


def stop_running(*, wait_s: float = 8.0) -> None:
    if not port_busy(bridge_mod.WEB_PORT):
        return
    req = urllib.request.Request(
        f"http://127.0.0.1:{bridge_mod.WEB_PORT}/store", headers={"X-Helper-Quit": "1"}
    )
    try:
        urllib.request.urlopen(req, timeout=3).read()
    except Exception:
        pass
    end = time.time() + wait_s
    while time.time() < end and port_busy(bridge_mod.WEB_PORT):
        time.sleep(0.3)


def set_keys(exe: Path) -> None:
    import winreg

    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as k:
        winreg.SetValueEx(k, APP_NAME, 0, winreg.REG_SZ, f'"{exe}"')
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, UNINSTALL_KEY) as k:
        for name, value in (
            ("DisplayName", DISPLAY_NAME),
            ("DisplayVersion", helper_store.HELPER_VERSION),
            ("Publisher", "문장 읽기"),
            ("DisplayIcon", str(exe)),
            ("InstallLocation", str(exe.parent)),
            ("UninstallString", f'"{exe}" --uninstall'),
        ):
            winreg.SetValueEx(k, name, 0, winreg.REG_SZ, value)
        winreg.SetValueEx(k, "NoModify", 0, winreg.REG_DWORD, 1)
        winreg.SetValueEx(k, "NoRepair", 0, winreg.REG_DWORD, 1)


def remove_keys() -> None:
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
            winreg.DeleteValue(k, APP_NAME)
    except OSError:
        pass
    try:
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, UNINSTALL_KEY)
    except OSError:
        pass


def launch_detached(exe: Path) -> None:
    flags = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    subprocess.Popen([str(exe)], creationflags=flags, close_fds=True)


def install(src: Path) -> int:
    dest = installed_exe()
    dest.parent.mkdir(parents=True, exist_ok=True)
    stop_running()
    for _ in range(10):
        try:
            shutil.copy2(src, dest)
            break
        except OSError:
            time.sleep(1)
    else:
        message("도우미를 바꾸지 못했어요.\n컴퓨터를 다시 켠 뒤 이 파일을 한 번 더 실행해 주세요.", error=True)
        return 1
    set_keys(dest)
    launch_detached(dest)
    message(
        "논문 전송 도우미를 설치했어요.\n"
        "컴퓨터를 켜면 저절로 켜져요.\n\n"
        "웹과 휴대폰 앱의 설정에서 연결을 확인할 수 있어요."
    )
    return 0


def uninstall() -> int:
    stop_running()
    remove_keys()
    folder = install_dir()
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    # This exe is still running, so cmd removes its folder after it exits.
    subprocess.Popen(
        f'cmd /c ping -n 3 127.0.0.1 >nul & rmdir /s /q "{folder}"', creationflags=flags, shell=False
    )
    message(
        "논문 전송 도우미를 지웠어요.\n\n"
        "이 컴퓨터에 보관한 논문 사본은 남겨 두었어요:\n"
        f"{helper_store.default_store_root()}"
    )
    return 0


def download_adb(dest: Path, log, url: str = ADB_ZIP_URL) -> Path | None:
    """Fetch adb from Google's platform-tools zip into dest/platform-tools."""
    target = dest / "platform-tools"
    tmp = dest / "platform-tools.zip.part"
    try:
        dest.mkdir(parents=True, exist_ok=True)
        with urllib.request.urlopen(url, timeout=120) as r, tmp.open("wb") as fh:
            shutil.copyfileobj(r, fh)
        target.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(tmp) as z:
            for name in ADB_FILES:
                with z.open(f"platform-tools/{name}") as src, (target / name).open("wb") as out:
                    shutil.copyfileobj(src, out)
        log("adb downloaded")
        return target / "adb.exe"
    except Exception as e:  # noqa: BLE001
        log(f"adb download failed: {type(e).__name__}")
        return None
    finally:
        try:
            tmp.unlink()
        except OSError:
            pass


def adb_finder(log, *, home: Path | None = None, fetch=download_adb):
    """A callable for watch_adb: the SDK's adb, ours, or None while ours downloads."""
    home = home or install_dir()
    state = {"at": -1e9, "busy": False}
    lock = threading.Lock()

    def worker() -> None:
        try:
            fetch(home, log)
        finally:
            with lock:
                state["busy"] = False

    def find() -> str | None:
        found = bridge_mod.find_adb()
        if found:
            return found
        ours = home / "platform-tools" / "adb.exe"
        if ours.is_file():
            return str(ours)
        with lock:
            if not state["busy"] and time.monotonic() - state["at"] >= ADB_RETRY_S:
                state["busy"] = True
                state["at"] = time.monotonic()
                threading.Thread(target=worker, daemon=True).start()
        return None

    return find


def run_helper() -> int:
    log = make_log()
    bridge = bridge_mod.Bridge(log=log)
    try:
        asyncio.run(
            bridge_mod.serve(
                probe_port=bridge_mod.PROBE_PORT,
                adb=adb_finder(log),
                bridge=bridge,
                store=helper_store.PaperStore(),
            )
        )
    except OSError as e:
        log(f"not started: {e}")
    return 0


def main(argv: list[str]) -> int:
    if "--uninstall" in argv:
        return uninstall()
    frozen = getattr(sys, "frozen", False)
    if frozen and "--run" not in argv:
        me = Path(sys.executable).resolve()
        if me != installed_exe().resolve():
            return install(me)
    return run_helper()


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
