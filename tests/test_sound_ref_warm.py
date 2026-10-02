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


def test_warm_says_so_when_this_instance_has_no_copy(monkeypatch):
    """design/383 - silence here is what hid a whole broken path for a day.

    A phone that opened a paper from its own disk and a phone that never asked at
    all both left no row, so the log could not tell them apart.
    """
    from sentence_reading.api import app as mod

    rows: list[tuple[str, dict]] = []
    done = threading.Event()

    def fake_emit(kind, **kw):
        rows.append((kind, kw))
        done.set()

    monkeypatch.setattr("sentence_reading.llm.evidence_bus.emit", fake_emit)
    monkeypatch.setattr(
        "sentence_reading.cache.paper_cache.load_cached_session",
        lambda cid, **k: None,
    )

    mod._warm_sound_refs("cache-gone")

    assert done.wait(5.0), "the warm thread said nothing at all"
    assert rows[0][0] == "sound_ref_warm"
    assert rows[0][1]["stage"] == "skip"
    assert rows[0][1]["details"]["warm_miss"] == "no_session"


def test_sound_warm_route_warms_a_paper_this_instance_can_pull(monkeypatch):
    """design/383 - the disk-open path reaches the warm through nothing else."""
    import asyncio
    import json

    from sentence_reading.api import app as mod

    warmed: list[str] = []
    monkeypatch.setattr(mod, "_paid_access_denied", lambda request: None)
    monkeypatch.setattr(mod, "_warm_sound_refs", lambda cid: warmed.append(cid))
    monkeypatch.setattr(
        "sentence_reading.llm.papers_gcs.refresh_paper_for_open",
        lambda cid: (True, "ok"),
    )

    res = asyncio.run(mod.cache_sound_warm(object(), " cache-abc "))

    assert warmed == ["cache-abc"]
    assert json.loads(res.body)["warm"] == "started"


def test_sound_warm_route_says_why_when_the_paper_is_gone(monkeypatch):
    import asyncio
    import json

    from sentence_reading.api import app as mod

    rows: list[tuple[str, dict]] = []
    warmed: list[str] = []
    monkeypatch.setattr(mod, "_paid_access_denied", lambda request: None)
    monkeypatch.setattr(mod, "_warm_sound_refs", lambda cid: warmed.append(cid))
    monkeypatch.setattr(
        "sentence_reading.llm.evidence_bus.emit",
        lambda kind, **kw: rows.append((kind, kw)),
    )
    monkeypatch.setattr(
        "sentence_reading.llm.papers_gcs.refresh_paper_for_open",
        lambda cid: (False, "gcs_pull_failed"),
    )

    res = asyncio.run(mod.cache_sound_warm(object(), "cache-abc"))

    assert warmed == []
    assert json.loads(res.body)["warm"] == "no_paper"
    assert rows[0][1]["details"]["warm_miss"] == "gcs_pull_failed"


def test_sound_warm_route_refuses_a_blank_cache_id(monkeypatch):
    import asyncio

    from sentence_reading.api import app as mod

    warmed: list[str] = []
    monkeypatch.setattr(mod, "_paid_access_denied", lambda request: None)
    monkeypatch.setattr(mod, "_warm_sound_refs", lambda cid: warmed.append(cid))

    res = asyncio.run(mod.cache_sound_warm(object(), "   "))

    assert res.status_code == 400
    assert warmed == []


def test_sound_warm_route_keeps_the_paid_gate(monkeypatch):
    """The warm costs synthesis calls, so it may not be the open door."""
    import asyncio

    from sentence_reading.api import app as mod

    warmed: list[str] = []
    sentinel = object()
    monkeypatch.setattr(mod, "_paid_access_denied", lambda request: sentinel)
    monkeypatch.setattr(mod, "_warm_sound_refs", lambda cid: warmed.append(cid))

    got = asyncio.run(mod.cache_sound_warm(object(), "cache-abc"))

    assert got is sentinel
    assert warmed == []


def test_the_warm_kind_is_allowed_through_the_door(monkeypatch):
    """design/383 - it was not, so every row from 0.3.418 on was dropped."""
    from sentence_reading.llm.evidence_kinds import ALLOWED_KINDS

    assert "sound_ref_warm" in ALLOWED_KINDS


def test_warm_reads_the_sentences_the_caller_sent(monkeypatch):
    """design/383 - a paper only the phone holds has to be warmed from its text."""
    from sentence_reading.api import app as mod

    seen: list[list[str]] = []
    done = threading.Event()

    def fake_warm(lines, **k):
        seen.append(list(lines))
        done.set()
        return {"warm_n": len(lines)}

    def no_session(cid, **k):
        raise AssertionError("the paper must not be read when texts were sent")

    monkeypatch.setattr(sr, "warm_paper", fake_warm)
    monkeypatch.setattr(
        "sentence_reading.cache.paper_cache.load_cached_session", no_session
    )
    monkeypatch.setattr(
        "sentence_reading.api.routes.tts._paper_speak_terms", lambda cid: {}
    )
    monkeypatch.setattr(
        "sentence_reading.llm.evidence_bus.emit", lambda *a, **k: None
    )
    # A sibling test may still hold the paper id in `_WARMING`; this path must
    # not look like a duplicate of a warm that already finished.
    mod._WARMING.clear()

    mod._warm_sound_refs("cache-phone", texts=["One two three.", "  ", "Four five."])

    assert done.wait(5.0), "the warm thread never ran"
    assert len(seen[0]) == 2, seen


def test_sound_warm_route_takes_the_sentences_over_the_paper(monkeypatch):
    import asyncio
    import json

    from sentence_reading.api import app as mod

    got: list[tuple[str, list[str] | None]] = []
    monkeypatch.setattr(mod, "_paid_access_denied", lambda request: None)
    monkeypatch.setattr(
        mod, "_warm_sound_refs", lambda cid, texts=None: got.append((cid, texts))
    )

    def no_pull(cid):
        raise AssertionError("GCS must not be touched when sentences came with it")

    monkeypatch.setattr(
        "sentence_reading.llm.papers_gcs.refresh_paper_for_open", no_pull
    )

    res = asyncio.run(
        mod.cache_sound_warm(
            object(), "cache-abc", {"texts": ["One two three.", "", "  Four.  "]}
        )
    )

    assert got == [("cache-abc", ["One two three.", "Four."])]
    body = json.loads(res.body)
    assert body["warm"] == "started" and body["n"] == 2


def test_sound_warm_route_still_falls_back_to_the_paper(monkeypatch):
    """An older phone sends no sentences; that path is all design/378 ever had."""
    import asyncio
    import json

    from sentence_reading.api import app as mod

    got: list[tuple[str, list[str] | None]] = []
    monkeypatch.setattr(mod, "_paid_access_denied", lambda request: None)
    monkeypatch.setattr(
        mod, "_warm_sound_refs", lambda cid, texts=None: got.append((cid, texts))
    )
    monkeypatch.setattr(
        "sentence_reading.llm.papers_gcs.refresh_paper_for_open",
        lambda cid: (True, "ok"),
    )

    res = asyncio.run(mod.cache_sound_warm(object(), "cache-abc", None))

    assert got == [("cache-abc", None)]
    assert json.loads(res.body)["warm"] == "started"


def test_sound_warm_route_caps_what_it_will_take(monkeypatch):
    from sentence_reading.api import app as mod

    many = mod._warm_texts_from({"texts": ["a b c"] * (mod._WARM_TEXTS_MAX + 50)})
    assert len(many) == mod._WARM_TEXTS_MAX
    long_one = mod._warm_texts_from({"texts": ["x" * (mod._WARM_TEXT_CHARS + 500)]})
    assert len(long_one[0]) == mod._WARM_TEXT_CHARS
    assert mod._warm_texts_from(None) == []
    assert mod._warm_texts_from({"texts": "not a list"}) == []
