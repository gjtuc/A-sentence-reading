"""design/169j — ProgressiveWriter DropOldest + flush off critical path."""

from __future__ import annotations

import os
import threading
import time

import pytest

os.environ.setdefault("ASR_SKIP_ENV_FILE", "1")

from sentence_reading.llm import evidence_bus as eb
from sentence_reading.llm.progressive_writer import ProgressiveWriter


@pytest.fixture()
def ev_tmp(tmp_path, monkeypatch):
    monkeypatch.setenv("ASR_EVIDENCE_BUS", "1")
    monkeypatch.setattr(eb, "local_events_path", lambda: tmp_path / "evidence.jsonl")
    monkeypatch.setattr(eb, "_gcs_events_object", lambda: None)
    monkeypatch.setattr(eb, "_RATE_MEM", {})
    return tmp_path


def test_writer_flush_runs_publish_and_durable(ev_tmp) -> None:
    pubs: list[int] = []
    durs: list[int] = []
    lock = threading.Lock()

    def publish() -> None:
        with lock:
            pubs.append(1)

    def durable() -> None:
        with lock:
            durs.append(1)

    w = ProgressiveWriter(
        publish_fn=publish,
        durable_fn=durable,
        debounce_s=0.5,
        job_id="job_test",
        cache_id="c1",
    )
    w.start()
    for _ in range(5):
        w.enqueue_publish(want_durable=False)
    w.enqueue_publish(want_durable=True)
    assert w.flush(timeout_s=10.0) is True
    assert sum(pubs) >= 1
    assert sum(durs) >= 1
    kinds = [r["kind"] for r in eb.list_events(limit=50)]
    assert "checkpoint" in kinds
    cps = [
        r["details"].get("checkpoint")
        for r in eb.list_events(limit=50)
        if r["kind"] == "checkpoint"
    ]
    assert "writer_flush" in cps
    assert "writer_done" in cps


def test_writer_drop_oldest_when_full(ev_tmp) -> None:
    gate = threading.Event()
    pubs: list[int] = []

    def publish() -> None:
        gate.wait(timeout=2.0)
        pubs.append(1)
        time.sleep(0.05)

    w = ProgressiveWriter(
        publish_fn=publish,
        durable_fn=None,
        maxsize=8,
        job_id="job_drop",
    )
    w.start()
    # Fill queue while first publish is blocked.
    for _ in range(40):
        w.enqueue_publish()
    gate.set()
    assert w.flush(timeout_s=10.0) is True
    assert w._drops >= 1
    cps = [
        r["details"].get("checkpoint")
        for r in eb.list_events(limit=80)
        if r["kind"] == "checkpoint"
    ]
    assert "writer_drop" in cps


def test_enqueue_does_not_block_caller() -> None:
    """Caller must return immediately even if publish is slow."""
    started = threading.Event()
    release = threading.Event()

    def publish() -> None:
        started.set()
        release.wait(timeout=5.0)

    w = ProgressiveWriter(publish_fn=publish, maxsize=4, job_id="job_nb")
    w.start()
    t0 = time.monotonic()
    w.enqueue_publish()
    # Wait until writer picked up work, then enqueue more without blocking.
    assert started.wait(timeout=2.0)
    for _ in range(20):
        w.enqueue_publish()
    elapsed = time.monotonic() - t0
    release.set()
    w.flush(timeout_s=5.0)
    assert elapsed < 1.0
