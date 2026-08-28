"""design/123 — progress restore precise + fail-closed (0.3.51)."""

from __future__ import annotations

import re
from pathlib import Path

from fastapi.testclient import TestClient

from sentence_reading.api.app import app

ROOT = Path(__file__).resolve().parents[1]
PROG = ROOT / "src" / "sentence_reading" / "static" / "progress.js"
APP_JS = ROOT / "src" / "sentence_reading" / "static" / "app.js"
PUB = ROOT / "mobile" / "pubspec.yaml"
GATE = ROOT / "mobile" / "lib" / "api" / "progress_gate.dart"
STORE = ROOT / "mobile" / "lib" / "api" / "progress_store.dart"
LIB = ROOT / "mobile" / "lib" / "state" / "library_controller.dart"
SHELL = ROOT / "mobile" / "lib" / "screens" / "home_shell.dart"


def test_status_progress_fail_closed_default() -> None:
    client = TestClient(app)
    st = client.get("/api/status").json()
    assert st["version"] == "0.3.78"
    assert st["progress_restore"] is True
    assert st["progress_fail_closed"] is True


def test_status_progress_fail_closed_kill(monkeypatch) -> None:
    monkeypatch.setenv("ASR_PROGRESS_FAIL_CLOSED", "0")
    client = TestClient(app)
    st = client.get("/api/status").json()
    assert st["progress_fail_closed"] is False


def test_progress_js_has_validate_and_fail_closed() -> None:
    src = PROG.read_text(encoding="utf-8")
    assert "validateProgressIndices" in src
    assert "failClosed" in src
    assert "loadProgressRow" in src
    assert "sentence_out_of_range" in src
    # Must not silently force clamp in default apply path when invalid.
    assert "do not mutate paper indices" in src or "ok: false" in src


def test_app_js_refuses_invalid_progress_before_papers() -> None:
    src = APP_JS.read_text(encoding="utf-8")
    assert "progressFailClosedFlag" in src
    assert "visibilitychange" in src
    assert "pagehide" in src
    assert "outcome.ok === false" in src


def test_mobile_progress_wiring() -> None:
    assert "0.3.78" in PUB.read_text(encoding="utf-8")
    gate = GATE.read_text(encoding="utf-8")
    assert "validateProgressIndices" in gate
    store = STORE.read_text(encoding="utf-8")
    assert "asr.progress.v1" in store or "progressPrefsKey" in gate
    lib = LIB.read_text(encoding="utf-8")
    assert "persistOpenedProgress" in lib
    assert "loadProgressRaw" in lib
    assert "validateProgressIndices" in lib
    shell = SHELL.read_text(encoding="utf-8")
    assert "persistOpenedProgress" in shell
    assert "AppLifecycleState.paused" in shell


def test_progress_js_mirror_validate_oob() -> None:
    """Mirror JS validate rules in Python for contract docs."""
    # Empty sentences
    assert _validate(0, 0, 0, 0) == "empty_sentences"
    assert _validate(1, 0, 5, 2) is None
    assert _validate(5, 0, 5, 2) == "sentence_out_of_range"
    assert _validate(0, 2, 5, 2) == "figure_out_of_range"
    assert _validate(0, 0, 5, 0) is None
    assert _validate(0, 1, 5, 0) == "figure_out_of_range"
    assert _validate("x", 0, 5, 2) == "non_integer_index"


def _validate(si, fi, sc, fc):
    """Python mirror of progress.js validateProgressIndices."""
    if not sc or sc < 1:
        return "empty_sentences"

    def strict_int(v):
        if isinstance(v, bool):
            return None
        if isinstance(v, int):
            return v
        if isinstance(v, float) and v == int(v):
            return int(v)
        if isinstance(v, str) and re.fullmatch(r"-?\d+", v.strip()):
            return int(v.strip())
        return None

    a = strict_int(si)
    b = strict_int(fi)
    if a is None or b is None:
        return "non_integer_index"
    if a < 0 or a >= sc:
        return "sentence_out_of_range"
    if not fc or fc < 1:
        if b != 0:
            return "figure_out_of_range"
    elif b < 0 or b >= fc:
        return "figure_out_of_range"
    return None
