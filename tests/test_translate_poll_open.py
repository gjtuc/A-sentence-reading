"""Translate poll must not stack open backfill tasks (design/99)."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from sentence_reading.api import app as app_mod
from sentence_reading.api.app import app
from sentence_reading.models import Figure, PaperSession, Sentence


@pytest.fixture(autouse=True)
def _clear_inflight() -> None:
    app_mod._OPEN_TRANSLATE_BACKFILL_INFLIGHT.clear()
    yield
    app_mod._OPEN_TRANSLATE_BACKFILL_INFLIGHT.clear()


def test_is_translate_poll_query() -> None:
    from sentence_reading.api.app import _is_translate_poll

    class _Req:
        def __init__(self, poll: str) -> None:
            self.query_params = {"poll": poll}

    assert _is_translate_poll(_Req("1")) is True
    assert _is_translate_poll(_Req("0")) is False


def test_spawn_open_translate_backfill_dedupes() -> None:
    app_mod._OPEN_TRANSLATE_BACKFILL_INFLIGHT.add("abcd1234ef00")
    spawned = 0

    def _fake_task(*_a, **_k) -> None:
        nonlocal spawned
        spawned += 1

    with patch.object(app_mod, "_open_translate_backfill_task", _fake_task):
        app_mod._spawn_open_translate_backfill(
            "abcd1234ef00",
            kind="pdf",
            doc_role="main",
        )
    assert spawned == 0
