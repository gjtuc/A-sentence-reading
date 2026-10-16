"""design/402 - local click jobs: the agent reads one short result file."""

from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CLICK = ROOT / "click"


def _runner():
    spec = importlib.util.spec_from_file_location("asr_click_run", CLICK / "_run.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_pytest_tally_and_failures():
    run = _runner()
    text = (
        "....F..\n"
        "FAILED tests/test_figure_pinch_vs_swipe.py::test_design_version - assert\n"
        "FAILED tests/test_new_thing.py::test_x\n"
        "2 failed, 88 passed, 1 warning in 214.81s (0:03:34)\n"
    )
    failed = run.pytest_failures(text)
    assert failed == [
        "tests/test_figure_pinch_vs_swipe.py::test_design_version",
        "tests/test_new_thing.py::test_x",
    ]
    assert run.pytest_tally(text).startswith("2 failed, 88 passed")
    old, new = run.split_known(failed, ["test_figure_pinch_vs_swipe.py"])
    assert old == ["tests/test_figure_pinch_vs_swipe.py::test_design_version"]
    assert new == ["tests/test_new_thing.py::test_x"]


def test_flutter_tally_and_failures():
    run = _runner()
    text = (
        "01:21 +492 -1: D:/x/mobile/test/widget_smoke_test.dart: login gate\n"
        "01:23 +493 -1: Some tests failed.\n"
        "\n"
        "Failing tests:\n"
        "  D:/x/mobile/test/advisory_title_smoke_test.dart: design/234 journal chrome\n"
    )
    assert run.flutter_tally(text) == "493 passed, 1 failed"
    assert run.flutter_failures(text) == [
        "D:/x/mobile/test/advisory_title_smoke_test.dart: design/234 journal chrome"
    ]
    assert run.flutter_tally("00:05 +12: All tests passed!\n") == "12 passed, 0 failed"


def test_app_version_reads_app_py():
    run = _runner()
    v = run.app_version()
    assert v.count(".") == 2 and all(p.isdigit() for p in v.split("."))


def test_ship_job_guards_before_ship_and_verify_before_apk():
    src = (CLICK / "_run.py").read_text(encoding="utf-8")
    body = src[src.index("def job_ship_install") :]
    order = [
        body.index("session_freshness_guard.py"),
        body.index("check_evidence_floor.py"),
        body.index("pre_deploy_guard.py"),
        body.index("ship_cloud_pair.ps1"),
        body.index("verify_live_status.py"),
        body.index("build_release_apk.ps1"),
        body.index('"install", "-r"'),
    ]
    assert order == sorted(order)
    assert "ASR_SKIP" not in src
    assert "git push" not in src


def test_click_folder_is_separate_and_logs_stay_local():
    assert "click/out/" in (ROOT / ".gitignore").read_text(encoding="utf-8")
    runner = (CLICK / "_job.cmd").read_text(encoding="ascii")
    assert "lifecycle_ga" not in runner
    for p in CLICK.glob("*.bat"):
        raw = p.read_bytes()
        raw.decode("ascii")
        assert b"\r\n" in raw and b"_job.cmd" in raw
