"""notes_revisions.js 계약 검증 — 브라우저 없이 동일 규칙 미러."""

from __future__ import annotations

import copy
from typing import Any


def empty_store() -> dict[str, Any]:
    return {"version": 2, "papers": {}}


def migrate_v1(v1: dict[str, Any] | None) -> dict[str, Any]:
    out = empty_store()
    if not isinstance(v1, dict):
        return out
    for pk, paper in v1.items():
        if not isinstance(paper, dict):
            continue
        out["papers"][pk] = {}
        for sid, body in paper.items():
            if not isinstance(body, str) or not body:
                continue
            out["papers"][pk][sid] = {
                "text": [{"rev": 1, "at": "t0", "body": body}],
                "voice": [],
            }
        if not out["papers"][pk]:
            del out["papers"][pk]
    return out


def latest_text(store: dict[str, Any], paper_key: str, sid: str) -> str:
    paper = (store.get("papers") or {}).get(paper_key) or {}
    entry = paper.get(sid) or {}
    text = entry.get("text") or []
    if not text:
        return ""
    return str(text[-1].get("body") or "")


def append_text(
    store: dict[str, Any], paper_key: str, sid: str, body: str
) -> tuple[dict[str, Any], bool, int | None]:
    store = copy.deepcopy(store) if store else empty_store()
    if not paper_key or not sid:
        return store, False, None
    trimmed = (body or "").rstrip()
    papers = store.setdefault("papers", {})
    paper = papers.setdefault(paper_key, {})
    entry = paper.get(sid) or {"text": [], "voice": []}
    text = list(entry.get("text") or [])
    prev = str(text[-1]["body"]) if text else ""
    if trimmed == prev:
        paper[sid] = {"text": text, "voice": entry.get("voice") or []}
        rev = text[-1]["rev"] if text else None
        return store, False, rev
    if not trimmed and not prev:
        return store, False, None
    next_rev = (text[-1]["rev"] + 1) if text else 1
    text.append({"rev": next_rev, "at": "t", "body": trimmed})
    paper[sid] = {"text": text, "voice": entry.get("voice") or []}
    return store, True, next_rev


def sentence_ids_in_section(sentences: list[dict], section: str) -> list[str]:
    if section is None or section == "":
        return []
    return [
        str(s["id"])
        for s in sentences
        if s and s.get("section") == section and s.get("id")
    ]


def test_migrate_v1_and_latest() -> None:
    v1 = {"cache:1": {"s-1": "hello", "s-2": ""}}
    store = migrate_v1(v1)
    assert store["version"] == 2
    assert latest_text(store, "cache:1", "s-1") == "hello"
    assert latest_text(store, "cache:1", "s-2") == ""


def test_append_only_and_skip_duplicate() -> None:
    store = empty_store()
    store, ok, rev = append_text(store, "p", "s", "a")
    assert ok and rev == 1
    store, ok, rev = append_text(store, "p", "s", "a")
    assert not ok and rev == 1
    store, ok, rev = append_text(store, "p", "s", "b")
    assert ok and rev == 2
    assert latest_text(store, "p", "s") == "b"
    assert len(store["papers"]["p"]["s"]["text"]) == 2


def test_edge_empty_keys_and_nonsense() -> None:
    store = empty_store()
    store, ok, rev = append_text(store, "", "s", "x")
    assert not ok and rev is None
    store, ok, rev = append_text(store, "p", "", "x")
    assert not ok and rev is None
    store, ok, rev = append_text(store, "p", "s", None)  # type: ignore[arg-type]
    assert not ok
    # 말도 안 되는 v1
    assert migrate_v1(None)["papers"] == {}
    assert migrate_v1({"x": "not-a-dict"})["papers"] == {}  # type: ignore[dict-item]
    assert migrate_v1({"x": {"s": 123}})["papers"] == {}  # type: ignore[dict-item]


def test_section_ids() -> None:
    sents = [
        {"id": "1", "section": "introduction"},
        {"id": "2", "section": "introduction"},
        {"id": "3", "section": "methods"},
        {"id": None, "section": "methods"},
    ]
    assert sentence_ids_in_section(sents, "introduction") == ["1", "2"]
    assert sentence_ids_in_section(sents, "methods") == ["3"]
    assert sentence_ids_in_section(sents, "") == []
    assert sentence_ids_in_section(sents, "missing") == []


def test_js_file_exports_contract() -> None:
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    js = (root / "src/sentence_reading/static/notes_revisions.js").read_text(
        encoding="utf-8"
    )
    for name in (
        "migrateV1Object",
        "appendTextRevision",
        "latestText",
        "sentenceIdsInSection",
        "asr.notes.v2",
    ):
        assert name in js


if __name__ == "__main__":
    test_migrate_v1_and_latest()
    test_append_only_and_skip_duplicate()
    test_edge_empty_keys_and_nonsense()
    test_section_ids()
    test_js_file_exports_contract()
    print("notes_revisions tests ok")
