"""design/408 - the web build keeps nothing on a local disk.

path_provider has no web plugin, so any store that asks for its folder on the web
throws MissingPluginException and the library shows it. Each folder lookup must
ask ``localDiskAvailable`` first.
"""

from __future__ import annotations

import pathlib
import re

import pytest

LIB = pathlib.Path(__file__).resolve().parents[1] / "mobile" / "lib"

GUARDED = [
    ("services/paper_disk_store.dart", "Future<Directory?> uidRoot()"),
    ("services/shadowing_disk_store.dart", "Future<Directory?> uidRoot()"),
    ("services/notes_local_archive.dart", "Future<File?> _storeFile()"),
    ("services/figure_disk_cache.dart", "Future<List<String>> listChildDirNames()"),
    ("services/figure_disk_cache.dart", "Future<Directory?> paperDir(String cacheId)"),
    ("services/figure_png_cache.dart", "Future<Directory?> _root()"),
    ("services/tts_audio_cache.dart", "Future<Directory?> _root()"),
    ("api/title_switch_store.dart", "Future<File?> _file()"),
    ("api/pdf_hash_cache_store.dart", "Future<Directory?> _dir()"),
    ("api/pdf_advisory_cache_store.dart", "Future<Directory?> _dir()"),
    ("services/paper_edit_stash.dart", "Future<PaperStashMeta?> readMeta(String cacheId)"),
    ("services/paper_edit_stash.dart", "Future<void> purgeOrphans(Set<String> knownCacheIds)"),
    ("practice_skill/skill_evidence_store.dart", "Future<void> append(Map<String, dynamic> event)"),
]


def _head(rel: str, signature: str, lines: int = 4) -> str:
    text = (LIB / rel).read_text(encoding="utf-8").replace("\r\n", "\n")
    at = text.index(signature)
    return "\n".join(text[at:].split("\n")[: lines + 1])


def test_switch_is_off_on_the_web():
    text = (LIB / "services/local_disk.dart").read_text(encoding="utf-8")
    assert re.search(r"bool get localDiskAvailable\s*=>\s*!kIsWeb\s*&&\s*!debugNoLocalDisk;", text)


@pytest.mark.parametrize(("rel", "signature"), GUARDED)
def test_folder_lookup_asks_the_switch_first(rel: str, signature: str):
    assert "!localDiskAvailable" in _head(rel, signature), f"{rel}: {signature}"


def test_documents_mirror_stays_unbound_without_a_disk():
    text = (LIB / "services/documents_mirror_store.dart").read_text(encoding="utf-8")
    assert "_uid = localDiskAvailable ? figureCacheSafeToken(" in text


def test_no_store_calls_path_provider_unguarded():
    """A new path_provider caller has to join the list above, or be wrapped in try."""
    known = {rel for rel, _ in GUARDED} | {
        "api/upload_reserve_store.dart",
        "api/upload_draft_store.dart",
        "practice_evidence/practice_evidence_store.dart",
        "screens/shadowing_practice_screen.dart",
    }
    found = {
        p.relative_to(LIB).as_posix()
        for p in LIB.rglob("*.dart")
        if re.search(r"get(Application\w+|Temporary)Directory\(", p.read_text(encoding="utf-8"))
    }
    assert found <= known, sorted(found - known)
