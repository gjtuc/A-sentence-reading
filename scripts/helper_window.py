# -*- coding: utf-8 -*-
"""design/497 — the Store helper's window (opened from the Start menu).

Shows what the running helper says on its probe port, how many papers this PC
keeps, and fetches Google's adb only when the user asks. Closing the window
leaves the helper running.
"""
from __future__ import annotations

import json
import os
import socket
import threading
from pathlib import Path

import helper_app
import helper_store
import usb_sync_bridge as bridge_mod

TITLE = "논문 전송 도우미"
REFRESH_MS = 2000
NOTE = "이 창을 닫아도 도우미는 계속 켜져 있어요. 컴퓨터를 켜면 저절로 켜져요."
ADB_NEED = "휴대폰을 USB 선으로 연결하려면 구글의 휴대폰 연결 도구(adb)가 필요해요."


def probe(port: int = bridge_mod.PROBE_PORT, timeout: float = 1.0) -> dict | None:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=timeout) as s:
            s.settimeout(timeout)
            line = s.makefile("r", encoding="utf-8").readline()
        hello = json.loads(line)
        return hello if isinstance(hello, dict) else None
    except (OSError, ValueError):
        return None


def count_papers(root: Path) -> int:
    try:
        return sum(
            1
            for acct in root.iterdir()
            if (acct / "papers").is_dir()
            for p in (acct / "papers").iterdir()
            if (p / "meta.json").is_file()
        )
    except OSError:
        return 0


def status_lines(hello: dict | None, papers: int) -> list[str]:
    if hello is None:
        return ["도우미를 켜는 중이에요…"]
    lines = ["● 도우미가 켜져 있어요"]
    lines.append("휴대폰: " + ("USB 선으로 연결됨" if hello.get("cable") else "연결 안 됨"))
    lines.append("웹 페이지: " + ("열려 있음" if hello.get("watch") else "열려 있지 않음"))
    lines.append(f"이 컴퓨터에 보관한 논문: {papers}개")
    return lines


def show_window() -> int:
    import tkinter as tk

    root_dir = helper_store.default_store_root()
    home = helper_app.install_dir()
    log = helper_app.make_log()

    win = tk.Tk()
    win.title(TITLE)
    win.resizable(False, False)
    pad = {"padx": 16, "pady": 4}
    font = ("Malgun Gothic", 10)

    tk.Label(win, text=TITLE, font=("Malgun Gothic", 14, "bold")).pack(anchor="w", padx=16, pady=(14, 6))
    status = tk.Label(win, text="", font=font, justify="left")
    status.pack(anchor="w", **pad)

    adb_box = tk.Frame(win)
    adb_text = tk.Label(adb_box, text=ADB_NEED, font=font, wraplength=360, justify="left")
    adb_text.pack(anchor="w")
    state = {"busy": False, "done": False}

    def fetch_adb() -> None:
        state["busy"] = True
        adb_btn.config(state="disabled", text="받는 중…")

        def work() -> None:
            ok = helper_app.download_adb(home, log) is not None

            def after() -> None:
                state["busy"] = False
                state["done"] = ok
                adb_btn.config(state="normal", text="휴대폰 연결 도구 받기")
                if not ok:
                    adb_text.config(text=ADB_NEED + "\n받지 못했어요. 인터넷 연결을 확인하고 다시 눌러 주세요.")

            win.after(0, after)

        threading.Thread(target=work, daemon=True).start()

    adb_btn = tk.Button(adb_box, text="휴대폰 연결 도구 받기", font=font, command=fetch_adb)
    adb_btn.pack(anchor="w", pady=(4, 0))

    tk.Label(win, text=NOTE, font=("Malgun Gothic", 9), fg="#555", wraplength=360, justify="left").pack(
        anchor="w", padx=16, pady=(10, 4)
    )
    buttons = tk.Frame(win)
    buttons.pack(anchor="e", padx=16, pady=(6, 14))

    def open_folder() -> None:
        root_dir.mkdir(parents=True, exist_ok=True)
        try:
            os.startfile(str(helper_app.real_path(root_dir)))  # type: ignore[attr-defined]
        except OSError:
            pass

    tk.Button(buttons, text="보관 폴더 열기", font=font, command=open_folder).pack(side="left", padx=(0, 8))
    tk.Button(buttons, text="닫기", font=font, command=win.destroy).pack(side="left")

    def refresh() -> None:
        hello = probe()
        status.config(text="\n".join(status_lines(hello, count_papers(root_dir))))
        need_adb = hello is not None and hello.get("adb") is False and not state["done"]
        if need_adb or state["busy"]:
            if not adb_box.winfo_ismapped():
                adb_box.pack(anchor="w", padx=16, pady=(8, 0), after=status)
        elif adb_box.winfo_ismapped():
            adb_box.pack_forget()
        win.after(REFRESH_MS, refresh)

    refresh()
    win.mainloop()
    return 0
