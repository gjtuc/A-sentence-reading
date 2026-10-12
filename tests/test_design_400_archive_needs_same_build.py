"""design/400 — an archived analysis is reused only by the build that made it."""

from __future__ import annotations

import inspect
import json

from sentence_reading.api import app as app_mod
from sentence_reading.cache import paper_cache as pc
from sentence_reading.llm.typography import PIPELINE_VERSION
from sentence_reading.models import PaperSession, Sentence


def _session() -> PaperSession:
    return PaperSession(
        title="Archive Build Stamp Paper Title Long Enough",
        sentences=[Sentence(id="1", text="Hello world sentence one.", section="abstract")],
        figures=[],
    )


def test_pipeline_name_moved_past_v24() -> None:
    assert int(PIPELINE_VERSION.removeprefix("rich-v")) >= 25


def test_analysis_stamps_and_resave_keeps_the_stamp(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(pc, "cache_root", lambda: tmp_path)
    first = pc.save_paper_session(_session(), source="pdf", analyzed_build="0.3.440")
    assert first is not None and first["analyzed_build"] == "0.3.440"
    cid = first["id"]
    again = pc.save_paper_session(_session(), source="pdf", force_cache_id=cid)
    assert again is not None and again["analyzed_build"] == "0.3.440"
    meta = json.loads((tmp_path / cid / "session.json").read_text(encoding="utf-8"))
    assert meta["analyzed_build"] == "0.3.440"
    assert pc.get_index_entry(cid)["analyzed_build"] == "0.3.440"


def test_unstamped_save_stays_unstamped(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(pc, "cache_root", lambda: tmp_path)
    entry = pc.save_paper_session(_session(), source="pdf")
    assert entry is not None and entry["analyzed_build"] == ""


def _hit(monkeypatch, build: str) -> object:
    hit = {"id": "abcd1234ef", "pipeline_version": PIPELINE_VERSION, "analyzed_build": build}
    monkeypatch.setattr(app_mod, "find_cached_by_text", lambda *_a, **_k: dict(hit))
    monkeypatch.setattr(app_mod, "load_cached_session", lambda _cid: (_session(), {}))
    return app_mod._try_cache_hit("Archive Build Stamp Paper Title Long Enough", "pdf")


def test_archive_from_another_build_is_not_reused(monkeypatch) -> None:
    assert _hit(monkeypatch, "0.3.439" if app_mod.app.version != "0.3.439" else "0.3.1") is None
    assert _hit(monkeypatch, "") is None
    assert _hit(monkeypatch, app_mod.app.version) is not None


def test_only_the_two_analysis_saves_pass_the_build() -> None:
    src = inspect.getsource(app_mod)
    assert src.count("analyzed_build=app.version,") == 2
    assert 'if str(hit.get("analyzed_build") or "") != app.version:' in src
