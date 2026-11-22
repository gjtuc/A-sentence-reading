# -*- coding: utf-8 -*-
"""design/512 - housekeeping loops run their first pass soon after boot."""

from __future__ import annotations

import os

import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_LOOPS = (
    "_evidence_rotate_loop",
    "_ingest_artifact_ttl_loop",
    "_transfer_pack_ttl_loop",
    "_paper_handoff_abandon_loop",
)


def _app_src() -> str:
    path = os.path.join(_ROOT, "src", "sentence_reading", "api", "app.py")
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def _loop_body(src: str, name: str) -> str:
    i = src.find(f"async def {name}(")
    assert i > 0, name
    j = src.find("\nasync def ", i + 10)
    k = src.find("\ndef ", i + 10)
    ends = [x for x in (j, k) if x > 0]
    return src[i : min(ends) if ends else len(src)]


def test_first_delay_default_and_cap(monkeypatch: pytest.MonkeyPatch) -> None:
    from sentence_reading.api.app import _housekeeping_first_delay_sec as first

    monkeypatch.delenv("ASR_HOUSEKEEPING_FIRST_DELAY_S", raising=False)
    assert first(3600) == 120
    assert first(60) == 60
    monkeypatch.setenv("ASR_HOUSEKEEPING_FIRST_DELAY_S", "-5")
    assert first(3600) == 0
    monkeypatch.setenv("ASR_HOUSEKEEPING_FIRST_DELAY_S", "nope")
    assert first(3600) == 120


def test_loops_sleep_first_delay_then_interval() -> None:
    src = _app_src()
    for name in _LOOPS:
        body = _loop_body(src, name)
        assert "_housekeeping_first_delay_sec(" in body, name
        assert "await asyncio.sleep(delay)" in body, name
        first_sleep = body.find("await asyncio.sleep(delay)")
        assert body.find("delay = ", first_sleep) > first_sleep, name


def test_rotate_runs_off_the_event_loop() -> None:
    body = _loop_body(_app_src(), "_evidence_rotate_loop")
    assert "asyncio.to_thread(_rotate_logs_and_tts_cache)" in body
    assert "rotate_events" not in body