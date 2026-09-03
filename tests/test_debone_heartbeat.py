"""Debone mid-chunk progress heartbeat (0.3.155 — Turn2 hang at 8/14)."""

from __future__ import annotations

import time

from sentence_reading.llm import debone as db


def test_debone_chunk_heartbeat_refires_on_progress() -> None:
    ticks: list[tuple[int, int]] = []

    def on_progress(done: int, total: int) -> None:
        ticks.append((done, total))

    with db._debone_chunk_heartbeat(
        on_progress, done=9, total=15, interval_s=0.05
    ):
        time.sleep(0.18)

    assert len(ticks) >= 2
    assert all(t == (9, 15) for t in ticks)


def test_process_chunk_with_guard_passes_heartbeat(monkeypatch) -> None:
    def on_progress(done: int, total: int) -> None:
        return None

    monkeypatch.setattr(
        db,
        "_process_one_chunk",
        lambda *a, **k: [("hello", "body")],
    )
    monkeypatch.setattr(db, "chunk_kind", lambda _c: "substantive")

    pairs, stat = db._process_chunk_with_guard(
        "hello world " * 20,
        0,
        3,
        "ctx",
        db.PaperContext(ok=True),
        on_progress=on_progress,
        progress_done=1,
        progress_total=4,
    )
    assert pairs
    assert stat.ok is True


def test_job_set_accepts_force_persist() -> None:
    from sentence_reading.api import app as app_mod

    text = open(app_mod.__file__, encoding="utf-8").read()
    assert "force_persist: bool = False" in text
    assert "다듬는 중 {chunk_done}/{chunk_total} · {elapsed}초" in text
