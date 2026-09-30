"""design/371 - the reader that says whether sound scoring is working.

The scorer was dead for three releases while the evidence stream held every
number that would have shown it. These tests are about the reader noticing.
"""

from __future__ import annotations

import importlib.util
import json
import pathlib

_SCRIPT = (
    pathlib.Path(__file__).resolve().parents[1] / "scripts" / "sound_score_verdict.py"
)


def _mod():
    spec = importlib.util.spec_from_file_location("sound_score_verdict", _SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _client(**details):
    base = {
        "phase": "align",
        "slot_code": "ok",
        "slot_hits": "111",
        "slot_pieces": "the | film | grew",
        "sound_pass_n": 3,
        "line_n": 50,
        "line_avg": 810,
        "line_used": 690,
    }
    base.update(details)
    return {
        "kind": "practice_skill_align",
        "source": "mobile",
        "app_version": "0.3.409",
        "details": base,
    }


def _server(**details):
    base = {"phase": "server_align", "sound_ref_code": "ready", "sound_ref_n": 3}
    base.update(details)
    return {"kind": "practice_skill_align", "source": "server", "details": base}


def _run(mod, rows, tmp_path, *args):
    path = tmp_path / "ev.jsonl"
    path.write_text(
        "".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8", newline="\n"
    )
    import sys

    argv = sys.argv
    sys.argv = ["sound_score_verdict.py", "--jsonl", str(path), *args]
    try:
        return mod.main()
    finally:
        sys.argv = argv


def test_design_371_a_dash_names_the_word_that_left_the_sheet() -> None:
    mod = _mod()
    off, off_n, slot_n = mod._words_off_the_sheet(
        [_client(slot_hits="-11", slot_pieces="the | film | grew")]
    )
    # Knowing the count is not enough. `the` leaving the sheet is the fix working;
    # `film` leaving it would mean the reference builder lost a word's sounds.
    assert off_n == 1
    assert slot_n == 3
    assert off["the"] == 1


def test_design_371_a_truncated_piece_list_still_counts() -> None:
    mod = _mod()
    # slot_pieces is capped at 400 characters in the evidence bus, so a long
    # sentence loses the tail names. Losing the count as well would hide it.
    off, off_n, _ = mod._words_off_the_sheet(
        [_client(slot_hits="11-", slot_pieces="the | film")]
    )
    assert off_n == 1
    assert off["?"] == 1


def test_design_371_a_healthy_window_passes(tmp_path) -> None:
    mod = _mod()
    rows = [_server(sound_ref_fail="none", sound_ref_run=0), _client()]
    assert _run(mod, rows, tmp_path) == 0


def test_design_371_a_failing_builder_is_a_fault(tmp_path) -> None:
    mod = _mod()
    rows = [
        _server(sound_ref_code="queued", sound_ref_fail="permissiondenied", sound_ref_status=403),
        _client(),
    ]
    assert _run(mod, rows, tmp_path) == 1


def test_design_371_a_builder_that_gave_up_is_a_fault(tmp_path) -> None:
    mod = _mod()
    rows = [_server(sound_ref_fail="none", sound_ref_run=5), _client()]
    assert _run(mod, rows, tmp_path) == 1


def test_design_371_takes_that_never_scored_are_a_fault(tmp_path) -> None:
    mod = _mod()
    # Every take answered but nothing judged is exactly the state design/371 was
    # written to end, and it used to read as a clean `ok`.
    rows = [
        _server(sound_ref_fail="none", sound_ref_run=0),
        _client(slot_code="sound_ref_missing"),
    ]
    assert _run(mod, rows, tmp_path) == 1


def test_design_371_no_reading_is_not_a_fault(tmp_path) -> None:
    mod = _mod()
    # Nobody having read is not the same as broken, or waiting for a person would
    # look like a defect and send someone chasing it.
    assert _run(mod, rows=[], tmp_path=tmp_path) == 2


def test_design_371_rows_older_than_the_release_are_not_a_fault(tmp_path) -> None:
    mod = _mod()
    old_server = {
        "kind": "practice_skill_align",
        "source": "server",
        "details": {"phase": "server_align"},
    }
    old_client = {
        "kind": "practice_skill_align",
        "source": "mobile",
        "app_version": "0.3.403",
        "details": {"phase": "align", "slot_code": "ok", "slot_hits": "111"},
    }
    assert _run(mod, [old_server, old_client], tmp_path) == 0


def test_design_371_a_named_version_must_carry_the_line(tmp_path) -> None:
    mod = _mod()
    rows = [
        _server(sound_ref_fail="none", sound_ref_run=0),
        {
            "kind": "practice_skill_align",
            "source": "mobile",
            "app_version": "0.3.409",
            "details": {"phase": "align", "slot_code": "ok", "slot_hits": "111"},
        },
    ]
    # Asking about a version and getting rows with no line means that build did
    # not ship what it claimed.
    assert _run(mod, rows, tmp_path, "--expect-version", "0.3.409") == 1
