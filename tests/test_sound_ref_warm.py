"""design/378 - a paper's references are built at analysis time, not reading time.

The point of warming is that the first pass through a new paper scores. The point
of warming *politely* is that it must not make the first pass worse: there is one
build worker, so handing it a whole paper at once would put the sentence on screen
behind every other sentence in the paper.
"""
from __future__ import annotations

import threading
import time

from sentence_reading.llm import sound_reference as sr


def test_warm_skips_what_is_already_built(monkeypatch):
    asked: list[str] = []
    monkeypatch.setattr(sr, "enabled", lambda: True)
    monkeypatch.setattr(sr, "reference_for", lambda *a, **k: {"words": []})
    monkeypatch.setattr(
        sr, "request_build", lambda text, **k: asked.append(text) or "queued"
    )

    out = sr.warm_paper(["one two three", "four five six"])

    assert asked == []
    assert out["warm_ready"] == 2
    assert out["warm_built"] == 0


def test_warm_asks_for_what_is_missing(monkeypatch):
    asked: list[str] = []
    monkeypatch.setattr(sr, "enabled", lambda: True)
    monkeypatch.setattr(sr, "reference_for", lambda *a, **k: None)

    def fake_build(text, **k):
        asked.append(text)
        return "queued"

    monkeypatch.setattr(sr, "request_build", fake_build)

    out = sr.warm_paper(["one two three", "", "   ", "four five six"])

    assert asked == ["one two three", "four five six"]
    assert out["warm_built"] == 2
    assert out["warm_failed"] == 0


def test_warm_waits_for_the_queue_to_clear(monkeypatch):
    """The reader's request must land behind one build, not behind the paper."""
    monkeypatch.setattr(sr, "enabled", lambda: True)
    monkeypatch.setattr(sr, "reference_for", lambda *a, **k: None)
    monkeypatch.setattr(sr, "WARM_POLL_S", 0.01)
    depth: list[int] = []
    pending = {"n": 0}

    def fake_pending() -> int:
        return pending["n"]

    def fake_build(text, **k):
        # Record how deep the queue was when this was submitted, then stand in
        # for the worker: the key sits pending until something clears it.
        depth.append(pending["n"])
        pending["n"] += 1
        threading.Timer(0.05, lambda: pending.__setitem__("n", pending["n"] - 1)).start()
        return "queued"

    monkeypatch.setattr(sr, "_pending_n", fake_pending)
    monkeypatch.setattr(sr, "request_build", fake_build)

    sr.warm_paper(["a b c", "d e f", "g h i"])

    # Never more than one build in flight because of the warm.
    assert depth == [0, 0, 0], depth


def test_warm_gives_up_after_repeated_failures(monkeypatch):
    asked: list[str] = []
    monkeypatch.setattr(sr, "enabled", lambda: True)
    monkeypatch.setattr(sr, "reference_for", lambda *a, **k: None)
    monkeypatch.setattr(sr, "_pending_n", lambda: 0)
    monkeypatch.setattr(sr, "_BUILD_RUN", sr.BUILD_GIVE_UP)
    monkeypatch.setattr(
        sr, "request_build", lambda text, **k: asked.append(text) or "queued"
    )

    out = sr.warm_paper(["a b c", "d e f"])

    assert asked == []
    assert out["warm_skipped"] == 2


def test_warm_is_off_when_the_feature_is_off(monkeypatch):
    monkeypatch.setattr(sr, "enabled", lambda: False)
    out = sr.warm_paper(["a b c"])
    assert out == {"warm_n": 0, "warm_off": 1}


def test_warm_survives_a_cache_read_that_throws(monkeypatch):
    asked: list[str] = []
    monkeypatch.setattr(sr, "enabled", lambda: True)
    monkeypatch.setattr(sr, "_pending_n", lambda: 0)

    def boom(*a, **k):
        raise OSError("disk went away")

    monkeypatch.setattr(sr, "reference_for", boom)
    monkeypatch.setattr(
        sr, "request_build", lambda text, **k: asked.append(text) or "queued"
    )

    out = sr.warm_paper(["a b c"])

    # An unreadable cache is not a reason to skip the sentence; ask for it.
    assert asked == ["a b c"]
    assert out["warm_built"] == 1


def test_warm_stops_at_its_budget(monkeypatch):
    asked: list[str] = []
    monkeypatch.setattr(sr, "enabled", lambda: True)
    monkeypatch.setattr(sr, "reference_for", lambda *a, **k: None)
    monkeypatch.setattr(sr, "_pending_n", lambda: 0)
    monkeypatch.setattr(sr, "WARM_BUDGET_S", -1.0)
    monkeypatch.setattr(
        sr, "request_build", lambda text, **k: asked.append(text) or "queued"
    )

    out = sr.warm_paper(["a b c", "d e f"])

    assert asked == []
    assert out["warm_skipped"] == 2


def test_finish_job_starts_the_warm(monkeypatch):
    """The wiring, not the warm: analysis end has to be what triggers it."""
    from sentence_reading.api import app as mod

    seen: list[list[str]] = []
    done = threading.Event()

    def fake_warm(lines, **k):
        seen.append(list(lines))
        done.set()
        return {"warm_n": len(lines)}

    class FakeSentence:
        def __init__(self, text: str) -> None:
            self.text = text

    class FakeSession:
        sentences = [FakeSentence("One two three."), FakeSentence("")]

    monkeypatch.setattr(sr, "warm_paper", fake_warm)
    monkeypatch.setattr(
        "sentence_reading.cache.paper_cache.load_cached_session",
        lambda cid, **k: (FakeSession(), {}),
    )
    monkeypatch.setattr(
        "sentence_reading.api.routes.tts._paper_speak_terms", lambda cid: {}
    )

    mod._warm_sound_refs("cache-abc")

    assert done.wait(5.0), "the warm thread never ran"
    assert seen and len(seen[0]) == 1
    assert "One two three" in seen[0][0]


def test_finish_job_warm_ignores_a_blank_cache_id(monkeypatch):
    from sentence_reading.api import app as mod

    called: list[int] = []
    monkeypatch.setattr(sr, "warm_paper", lambda lines, **k: called.append(1))

    mod._warm_sound_refs("")
    mod._warm_sound_refs("   ")
    time.sleep(0.1)

    assert called == []
