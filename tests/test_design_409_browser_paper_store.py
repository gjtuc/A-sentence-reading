"""design/409 - the web keeps papers in browser storage and never ACKs a handoff.

An ACK wipes the server copy (design/185). A browser that ACKs first leaves the
phone, which still owns the paper, with nothing to pull.
"""

from __future__ import annotations

import pathlib
import re

LIB = pathlib.Path(__file__).resolve().parents[1] / "mobile" / "lib"


def _read(rel: str) -> str:
    return (LIB / rel).read_text(encoding="utf-8").replace("\r\n", "\n")


def test_browser_disk_only_on_the_web():
    text = _read("services/disk_fs.dart")
    assert "import 'browser_disk_stub.dart'\n    if (dart.library.js_interop) 'browser_disk_web.dart';" in text
    assert "DiskFs? openBrowserDisk() => null;" in _read("services/browser_disk_stub.dart")
    web = _read("services/browser_disk_web.dart")
    assert "indexedDB.open(" in web
    assert "storage.persist()" in web


def test_paper_store_reads_and_writes_through_disk_fs():
    text = _read("services/paper_disk_store.dart")
    body = text[text.index("Future<DiskFile?> _indexFile()"):]
    source = body.index("Future<String?> localSourcePath(")
    body = body[:source] + body[body.index("Future<bool> hasLocalSource("):]
    assert not re.search(r"(?<!Disk)\b(File|Directory)\(", body)
    assert "uidRoot()" not in body
    assert "if (!browserDiskAvailable) return null;" in text


def test_web_copy_never_acks():
    text = _read("state/library_controller.dart")
    at = text.index("_client.postHandoffAck(")
    before = text[at - 400:at]
    assert "final copyOnly = !localDiskAvailable;" in before
    assert "copyOnly\n          ? const <String, dynamic>{'ok': true, 'wiped': false}" in before
