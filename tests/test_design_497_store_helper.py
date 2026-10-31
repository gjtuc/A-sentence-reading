# -*- coding: utf-8 -*-
"""design/497 — the Microsoft Store helper: no self-install, a startup task, adb on a click."""
from __future__ import annotations

import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

pytest.importorskip("websockets")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import build_helper_msix as bm  # noqa: E402
import helper_app  # noqa: E402
import helper_window  # noqa: E402
import usb_sync_bridge as bridge_mod  # noqa: E402


def test_packaged_startup_copy_serves_without_adb_download(monkeypatch, tmp_path: Path) -> None:
    calls: list = []
    monkeypatch.setattr(helper_app, "port_busy", lambda port: False)
    monkeypatch.setattr(helper_app, "run_helper", lambda **kw: calls.append(kw) or 0)
    me = tmp_path / "SentenceReadingHelperStartup.exe"
    assert helper_app.run_packaged(me, [], show=lambda: 1 / 0) == 0
    assert calls == [{"auto_adb": False}]

    monkeypatch.setattr(helper_app, "port_busy", lambda port: True)
    calls.clear()
    assert helper_app.run_packaged(me, []) == 0
    assert calls == [], "already running"


def test_packaged_start_menu_copy_starts_the_helper_and_shows_the_window(monkeypatch, tmp_path: Path) -> None:
    started: list = []
    monkeypatch.setattr(helper_app.subprocess, "Popen", lambda cmd, **kw: started.append(cmd))
    monkeypatch.setattr(helper_app, "run_helper", lambda **kw: 1 / 0)
    me = tmp_path / "SentenceReadingHelper.exe"
    (tmp_path / "SentenceReadingHelperStartup.exe").write_bytes(b"")
    shown: list = []

    monkeypatch.setattr(helper_app, "port_busy", lambda port: False)
    assert helper_app.run_packaged(me, [], show=lambda: shown.append(1) or 0) == 0
    assert started == [[str(tmp_path / "SentenceReadingHelperStartup.exe")]]
    assert shown == [1]

    monkeypatch.setattr(helper_app, "port_busy", lambda port: True)
    started.clear()
    assert helper_app.run_packaged(me, [], show=lambda: 0) == 0
    assert started == []


def test_packaged_main_never_installs(monkeypatch) -> None:
    monkeypatch.setattr(helper_app.sys, "frozen", True, raising=False)
    monkeypatch.setattr(helper_app, "is_packaged", lambda: True)
    monkeypatch.setattr(helper_app, "install", lambda src: 1 / 0)
    monkeypatch.setattr(helper_app, "uninstall", lambda: 1 / 0)
    monkeypatch.setattr(helper_app, "run_packaged", lambda me, argv: 7)
    assert helper_app.main([]) == 7
    assert helper_app.main(["--uninstall"]) == 7


def test_adb_is_fetched_only_when_asked(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(bridge_mod, "find_adb", lambda: None)
    fetched: list = []
    find = helper_app.adb_finder(lambda *_: None, home=tmp_path, fetch=lambda *a: fetched.append(a), auto=False)
    assert find() is None
    assert fetched == []
    (tmp_path / "platform-tools").mkdir()
    (tmp_path / "platform-tools" / "adb.exe").write_bytes(b"")
    assert find() == str(tmp_path / "platform-tools" / "adb.exe")


def test_hello_says_whether_adb_was_found() -> None:
    b = bridge_mod.Bridge(log=lambda *_: None)
    assert bridge_mod.helper_hello(b)["adb"] is None
    b.adb = False
    assert bridge_mod.helper_hello(b)["adb"] is False


def test_folder_button_opens_the_package_copy(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    store = tmp_path / "SentenceReading" / "helper-papers"
    assert helper_app.real_path(store, "Fam_123") == store
    real = tmp_path / "Packages" / "Fam_123" / "LocalCache" / "Local" / "SentenceReading" / "helper-papers"
    real.mkdir(parents=True)
    assert helper_app.real_path(store, "Fam_123") == real
    assert helper_app.real_path(store, "") == store


def test_window_lines_and_paper_count(tmp_path: Path) -> None:
    (tmp_path / "acct1" / "papers" / "p1").mkdir(parents=True)
    (tmp_path / "acct1" / "papers" / "p1" / "meta.json").write_text("{}", encoding="utf-8")
    (tmp_path / "acct1" / "papers" / "half").mkdir()
    assert helper_window.count_papers(tmp_path) == 1
    assert helper_window.count_papers(tmp_path / "missing") == 0
    assert helper_window.status_lines(None, 0) == ["도우미를 켜는 중이에요…"]
    lines = helper_window.status_lines({"cable": True, "watch": False}, 3)
    assert "휴대폰: USB 선으로 연결됨" in lines and "이 컴퓨터에 보관한 논문: 3개" in lines


def test_manifest_has_startup_task_and_store_version() -> None:
    assert bm.package_version("0.3.510") == "1.3.510.0"
    identity = json.loads((ROOT / "scripts" / "helper_msix_identity.json").read_text(encoding="utf-8"))
    xml = bm.manifest(identity, "1.3.510.0")
    ns = {
        "m": "http://schemas.microsoft.com/appx/manifest/foundation/windows10",
        "desktop": "http://schemas.microsoft.com/appx/manifest/desktop/windows10",
        "rescap": "http://schemas.microsoft.com/appx/manifest/foundation/windows10/restrictedcapabilities",
    }
    doc = ET.fromstring(xml.encode("utf-8"))
    assert doc.find("m:Identity", ns).get("Version") == "1.3.510.0"
    app = doc.find("m:Applications/m:Application", ns)
    assert app.get("Executable") == "helper\\SentenceReadingHelper.exe"
    ext = app.find("m:Extensions/desktop:Extension", ns)
    assert ext.get("Category") == "windows.startupTask"
    assert ext.get("Executable") == "helper\\SentenceReadingHelperStartup.exe"
    assert ext.find("desktop:StartupTask", ns).get("Enabled") == "true"
    assert doc.find("m:Capabilities/rescap:Capability", ns).get("Name") == "runFullTrust"


def test_privacy_page_and_store_link(monkeypatch) -> None:
    from fastapi.testclient import TestClient

    from sentence_reading.api.app import app
    from sentence_reading.llm import mobile_apk_gcs as mag

    client = TestClient(app)
    page = client.get("/privacy")
    assert page.status_code == 200
    assert "개인정보 처리방침" in page.text and "논문 전송 도우미" in page.text

    monkeypatch.delenv("ASR_HELPER_STORE_URL", raising=False)
    monkeypatch.setattr(mag, "HELPER_STORE_ID", "")
    assert client.get("/api/status").json()["helper_store_url"] is None
    monkeypatch.setattr(mag, "HELPER_STORE_ID", "9NTEST123")
    assert mag.helper_store_url() == "https://apps.microsoft.com/detail/9NTEST123"
    monkeypatch.setenv("ASR_HELPER_STORE_URL", "https://example.test/x")
    assert mag.helper_store_url() == "https://example.test/x"


def test_privacy_page_is_open_without_login(monkeypatch) -> None:
    from sentence_reading.llm import login_required as lr

    assert lr.is_login_public_path("/privacy")
    assert lr.is_login_public_path("/privacy/")
    assert not lr.is_login_public_path("/privacy-other")
