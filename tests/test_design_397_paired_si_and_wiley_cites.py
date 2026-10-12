"""design/397 — a supplementary that was paired must survive the library sweep, and
Wiley citation marks must be read as citations.

1. The server sweeper must not mark a job lost when reclaim says another instance
   already finished it (`job_already_done`). The stale copy adopts the shared state.
2. `[ 5f, 7 ]`, `[1a,e]`, `[ 1 ]` are citations; `[001]` is a zone axis.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _run_one_sweep(monkeypatch, *, gcs_meta: dict, reclaim_reason: str):
    from sentence_reading.api import app as app_mod
    from sentence_reading.llm import ingest_jobs_gcs as ij
    from sentence_reading.llm import ingest_lease_obs as ilo
    from sentence_reading.llm import ingest_stall

    ticks = iter([0.001, 0])
    monkeypatch.setattr(ingest_stall, "sweeper_interval_sec", lambda: next(ticks))
    monkeypatch.setattr(ingest_stall, "sweep_candidate", lambda job: "reclaim")
    monkeypatch.setattr(ilo, "gcs_snapshot", lambda jid, owner: {"gcs_done": True})
    emitted: list[tuple[str, dict]] = []
    monkeypatch.setattr(
        ilo,
        "emit_dual",
        lambda kind, **kw: emitted.append((kind, kw.get("details") or {})),
    )
    monkeypatch.setattr(ij, "load_ingest_job", lambda jid, owner_uid=None: dict(gcs_meta))

    async def _reclaim(jid, owner):
        app_mod._JOBS[jid]["_last_reclaim_reason"] = reclaim_reason
        return False

    monkeypatch.setattr(app_mod, "_reclaim_ingest_job_from_gcs", _reclaim)
    failed: list[str] = []
    monkeypatch.setattr(
        app_mod, "_fail_job_terminal", lambda jid, *a, **k: failed.append(jid)
    )
    jid = "job_397aaaaaaaaa"
    monkeypatch.setitem(
        app_mod._JOBS,
        jid,
        {"owner_uid": "u397", "stage": "ready", "percent": 88, "done": False},
    )
    asyncio.run(app_mod._ingest_sweeper_loop())
    return app_mod._JOBS[jid], failed, emitted


def test_already_done_elsewhere_is_not_lost(monkeypatch) -> None:
    job, failed, emitted = _run_one_sweep(
        monkeypatch,
        gcs_meta={"done": True, "stage": "done", "percent": 100},
        reclaim_reason="job_already_done",
    )
    assert failed == []
    assert job["done"] is True and job["percent"] == 100
    kills = [d for k, d in emitted if k == "sweep_kill_decision"]
    assert kills and kills[-1]["decision"] == "skipped_already_terminal"
    results = [d for k, d in emitted if d.get("action") == "reclaim_result"]
    assert results and results[-1]["will_mark_lost"] is False


def test_expired_lease_still_marks_lost(monkeypatch) -> None:
    _job, failed, _emitted = _run_one_sweep(
        monkeypatch,
        gcs_meta={"done": False, "stage": "ready", "percent": 88},
        reclaim_reason="upload_missing",
    )
    assert failed == ["job_397aaaaaaaaa"]


def test_wiley_part_letters_are_citations() -> None:
    from sentence_reading.cite_refs import parse_cite_numbers

    assert parse_cite_numbers("catalytic performance. [ 1 ]") == [1]
    assert parse_cite_numbers("sites is increased. [ 5f, 7 ]") == [5, 7]
    assert parse_cite_numbers("reaction (ORR). [ 1a,e ]") == [1]
    assert parse_cite_numbers("polyol method, [ 8b, 11 ] and") == [8, 11]
    assert parse_cite_numbers("as shown before [5a–c, 9]") == [5, 9]
    assert parse_cite_numbers("[17c] These results") == [17]


def test_zone_axis_is_not_a_citation() -> None:
    from sentence_reading.cite_refs import parse_cite_numbers, strip_cite_markers_for_display

    assert parse_cite_numbers("oriented along the Pt [001] zone axis") == []
    assert "[001]" in strip_cite_markers_for_display("along the Pt [001] zone axis")


def test_display_strips_wiley_marks() -> None:
    from sentence_reading.cite_refs import strip_cite_markers_for_display

    out = strip_cite_markers_for_display("the active sites is increased. [ 5f, 7 ]")
    assert out == "the active sites is increased."
    assert strip_cite_markers_for_display("wet impregnation, [ 10 ] the") == (
        "wet impregnation, the"
    )


def test_three_copies_share_the_bracket_rule() -> None:
    py = (ROOT / "src/sentence_reading/cite_refs.py").read_text(encoding="utf-8")
    js = (ROOT / "src/sentence_reading/static/cite_refs.js").read_text(encoding="utf-8")
    dart = (ROOT / "mobile/lib/api/cite_refs.dart").read_text(encoding="utf-8")
    core = r"\[\s*(?!0)(\d+[a-z]?(?:\s*[-–—,]\s*(?:\d+[a-z]?|[a-z](?![a-z])))*)\s*\]"
    assert core in py and core in js and core in dart


def test_residue_sweep_keeps_folded_si() -> None:
    src = (ROOT / "mobile/lib/state/library_controller.dart").read_text(encoding="utf-8")
    body = src.split("Future<void> sweepLocalResidues(", 1)[1].split("var deleted", 1)[0]
    assert "residueLibraryIds(" in body and "pairedCacheId" in body
