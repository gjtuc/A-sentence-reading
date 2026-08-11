"""design/106 — Gemini call hard timeouts for quality / vision."""

from __future__ import annotations

import concurrent.futures

import pytest


def _patch_executor_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    class _Fut:
        def result(self, timeout=None):
            raise concurrent.futures.TimeoutError()

    class _Pool:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def submit(self, fn, *args, **kwargs):
            return _Fut()

    monkeypatch.setattr(concurrent.futures, "ThreadPoolExecutor", _Pool)


def test_call_gemini_text_timeout(monkeypatch: pytest.MonkeyPatch):
    from sentence_reading.llm import debone

    monkeypatch.setattr(debone, "gemini_api_key", lambda: "fake-key")
    _patch_executor_timeout(monkeypatch)
    with pytest.raises(TimeoutError, match="timed out"):
        debone._call_gemini("sys", "user", timeout_s=0.05)


def test_call_gemini_vision_timeout(monkeypatch: pytest.MonkeyPatch):
    from sentence_reading.llm import vision_ocr

    monkeypatch.setattr(vision_ocr, "gemini_api_key", lambda: "fake-key")
    _patch_executor_timeout(monkeypatch)
    with pytest.raises(TimeoutError, match="timed out"):
        vision_ocr._call_gemini_vision("sys", "user", b"png", timeout_s=0.05)


def test_quality_map_timeout_falls_back_text_ok(monkeypatch: pytest.MonkeyPatch):
    from sentence_reading.llm import extract_quality as eq

    monkeypatch.setattr(eq, "gemini_api_key", lambda: "fake-key")

    def boom(*_a, **_k):
        raise TimeoutError("Gemini text timed out after 90s")

    monkeypatch.setattr("sentence_reading.llm.debone._call_gemini", boom)
    pages = ["Enough alphanumeric text " * 20 for _ in range(3)]
    decision = eq.gemini_quality_map(pages)
    assert decision.verdict == "text_ok"
    assert decision.source == "fallback"
    assert "quality_map_failed" in (decision.warning or "")
