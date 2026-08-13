"""영→한 다단계 번역 (0.3.3 · design/36)."""

from __future__ import annotations

import sys
import types as pytypes
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from sentence_reading.api.app import app
from sentence_reading.llm import translate as tr

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def _clear_cache() -> None:
    tr.clear_translate_cache_for_tests()
    yield
    tr.clear_translate_cache_for_tests()


def _install_stage_gemini(
    monkeypatch: pytest.MonkeyPatch, replies: list[str | None]
) -> list[str]:
    """순서대로 generate_content 응답. None → 빈 텍스트."""
    calls: list[str] = []
    queue = list(replies)

    class _Models:
        def generate_content(self, **kwargs):  # noqa: ANN003
            calls.append(str(kwargs.get("contents") or ""))
            text = queue.pop(0) if queue else ""
            return SimpleNamespace(text=text or "   ", candidates=[])

    class _Client:
        def __init__(self, api_key: str | None = None) -> None:
            self.models = _Models()

    class _GenerateContentConfig:
        def __init__(self, **kwargs) -> None:  # noqa: ANN003
            self.kwargs = kwargs

    google = pytypes.ModuleType("google")
    google_genai = pytypes.ModuleType("google.genai")
    google_genai_types = pytypes.ModuleType("google.genai.types")
    google_genai.Client = _Client
    google_genai.types = google_genai_types
    google_genai_types.GenerateContentConfig = _GenerateContentConfig
    google.genai = google_genai
    monkeypatch.setitem(sys.modules, "google", google)
    monkeypatch.setitem(sys.modules, "google.genai", google_genai)
    monkeypatch.setitem(sys.modules, "google.genai.types", google_genai_types)
    monkeypatch.setattr(tr, "gemini_api_key", lambda: "fake-key")
    monkeypatch.setattr(tr, "gemini_model", lambda: "gemini-test")
    return calls


def test_status_pipeline_flag() -> None:
    st = TestClient(app).get("/api/status").json()
    assert st["version"] == "0.3.50"
    assert st["translate_pipeline"] is True
    assert "translate_en_ko" in st


def test_design_36_contract() -> None:
    design = (ROOT / "docs" / "design" / "36-translate-pipeline.md").read_text(
        encoding="utf-8"
    )
    assert "0.2.44" in design
    assert "draft" in design and "sense" in design and "polish" in design
    assert "fail-soft" in design.lower() or "Fail-soft" in design
    assert "Live Enable" in design or "IPS" in design


def test_ui_sends_pipeline_mode() -> None:
    js = (ROOT / "src" / "sentence_reading" / "static" / "app.js").read_text(
        encoding="utf-8"
    )
    assert 'mode: "pipeline"' in js or "mode: translatePrefs.mode" in js
    assert "design/35·36" in js or "design/36" in js
    assert "pipeline" in js
    html = TestClient(app).get("/").text
    assert "app.js?v=0.3.49" in html


def test_pipeline_full_three_stages(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _install_stage_gemini(
        monkeypatch, ["초안", "감수본", "윤문본"]
    )
    out = tr.translate_en_to_ko_pipeline("Catalyst activity increased.")
    assert out["ok"] is True
    assert out["ko"] == "윤문본"
    assert out["mode"] == "pipeline"
    assert out["stages_done"] == ["draft", "sense", "polish"]
    assert out["cached"] is False
    assert len(calls) == 3

    out2 = tr.translate_en_to_ko_pipeline("Catalyst activity increased.")
    assert out2["cached"] is True
    assert out2["ko"] == "윤문본"
    assert len(calls) == 3


def test_pipeline_failsoft_sense_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_stage_gemini(monkeypatch, ["초안만", None, "윤문"])
    out = tr.translate_en_to_ko_pipeline("Hello catalysts.")
    assert out["ok"] is True
    # sense empty → keep draft; polish still runs on draft
    assert out["ko"] == "윤문"
    assert out["stages_done"] == ["draft", "polish"]


def test_pipeline_failsoft_polish_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []
    n = {"i": 0}

    def fake_gen(system: str, user: str) -> str | None:
        n["i"] += 1
        calls.append(system[:20])
        if n["i"] == 1:
            return "초안"
        if n["i"] == 2:
            return "감수"
        raise RuntimeError("polish boom")

    monkeypatch.setattr(tr, "gemini_api_key", lambda: "k")
    monkeypatch.setattr(tr, "_gemini_generate", fake_gen)
    out = tr.translate_en_to_ko_pipeline("X")
    assert out["ok"] is True
    assert out["ko"] == "감수"
    assert out["stages_done"] == ["draft", "sense"]


def test_pipeline_draft_fail(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_stage_gemini(monkeypatch, [None])
    out = tr.translate_en_to_ko_pipeline("Something.")
    assert out == {"ok": False, "error": "translate_failed"}


def test_dispatch_invalid_and_simple(monkeypatch: pytest.MonkeyPatch) -> None:
    assert tr.translate_dispatch("Hi", "nope")["error"] == "invalid_mode"
    _install_stage_gemini(monkeypatch, ["단순"])
    out = tr.translate_dispatch("Hi", "simple")
    assert out["mode"] == "simple"
    assert out["ko"] == "단순"
    assert out["stages_done"] == ["draft"]


def test_api_default_pipeline(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("sentence_reading.api.app.gemini_available", lambda: True)

    def fake(text: str, mode: str = "pipeline") -> dict:
        return {
            "ok": True,
            "ko": "결과",
            "cached": False,
            "mode": mode,
            "stages_done": ["draft", "sense", "polish"]
            if mode == "pipeline"
            else ["draft"],
        }

    monkeypatch.setattr(
        "sentence_reading.llm.translate.translate_dispatch", fake
    )
    client = TestClient(app)
    r = client.post("/api/translate", json={"text": "Hi"})
    body = r.json()
    assert body["ok"] is True
    assert body["mode"] == "pipeline"
    assert body["stages_done"] == ["draft", "sense", "polish"]

    bad = client.post("/api/translate", json={"text": "Hi", "mode": "weird"})
    # dispatch returns invalid_mode
    monkeypatch.setattr(
        "sentence_reading.llm.translate.translate_dispatch",
        lambda t, m="pipeline": {"ok": False, "error": "invalid_mode"},
    )
    bad = client.post("/api/translate", json={"text": "Hi", "mode": "weird"})
    assert bad.json()["error"] == "invalid_mode"


def test_edges_empty_too_long_no_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(tr, "gemini_api_key", lambda: "k")
    assert tr.translate_en_to_ko_pipeline("")["error"] == "empty"
    assert tr.translate_en_to_ko_pipeline("a" * (tr._MAX_CHARS + 1))["error"] == "too_long"
    monkeypatch.setattr(tr, "gemini_api_key", lambda: "")
    assert tr.translate_en_to_ko_pipeline("Hi")["error"] == "gemini_unavailable"
