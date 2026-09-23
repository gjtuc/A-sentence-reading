"""design/318 — shared JSONL store; buses keep kinds and kill switches."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from sentence_reading.llm import jsonl_store as jl

ROOT = Path(__file__).resolve().parents[1]
DESIGN = ROOT / "docs/design/318-jsonl-store.md"
README = ROOT / "docs/design/README.md"
BUS = ROOT / "src/sentence_reading/llm/evidence_bus.py"
OPS = ROOT / "src/sentence_reading/llm/ops_events.py"
ERR = ROOT / "src/sentence_reading/llm/error_logs.py"
AUD = ROOT / "src/sentence_reading/llm/upload_audit_log.py"


def test_design_318_locked() -> None:
    text = DESIGN.read_text(encoding="utf-8")
    assert "Status: **locked" in text
    assert "jsonl_store.py" in text
    assert "FROZEN_KINDS" in text
    assert "318-jsonl-store.md" in README.read_text(encoding="utf-8")


def test_buses_call_shared_store() -> None:
    for path in (BUS, OPS, ERR, AUD):
        src = path.read_text(encoding="utf-8")
        assert "jsonl_store as _jl" in src
        assert "pull_events_raw" in src
        assert "push_events_raw" in src
        assert "parse_jsonl_events" in src
        assert "encode_jsonl_events" in src
        assert "trim_jsonl_events" in src


def test_parse_and_retain_keep_missing_ts() -> None:
    raw = (
        b'{"id":"a","ts":"2010-01-01T00:00:00Z"}\n'
        b'{"id":"b"}\n'
        b'not-json\n'
        b'{"no":"id"}\n'
        b'{"id":"c","ts":"2026-01-01T00:00:00Z"}\n'
    )
    rows = jl.parse_jsonl_events(raw)
    assert [r["id"] for r in rows] == ["a", "b", "c"]
    now = datetime(2026, 1, 8, tzinfo=timezone.utc)
    kept, dropped = jl.filter_retained(rows, keep_days=7, now=now)
    assert [r["id"] for r in kept] == ["b", "c"]
    assert dropped == 1


def test_trim_count_then_half_on_bytes() -> None:
    rows = [{"id": f"e{i}", "pad": "x" * 20} for i in range(10)]
    trimmed = jl.trim_jsonl_events(rows, max_keep=4, max_body_bytes=10_000_000)
    assert [r["id"] for r in trimmed] == ["e6", "e7", "e8", "e9"]
    huge = jl.trim_jsonl_events(rows, max_keep=100, max_body_bytes=80)
    assert huge == rows[len(rows) // 2 :]
    assert jl.encode_jsonl_events([]) == b""


def test_filter_retained_uses_at_when_ts_missing() -> None:
    now = datetime(2026, 6, 1, tzinfo=timezone.utc)
    rows = [
        {"id": "old", "at": "2026-01-01T00:00:00Z"},
        {"id": "new", "at": "2026-05-20T00:00:00Z"},
        {"id": "notime"},
    ]
    kept, dropped = jl.filter_retained(rows, keep_days=90, now=now)
    assert [r["id"] for r in kept] == ["new", "notime"]
    assert dropped == 1
