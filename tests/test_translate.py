"""영→한 단순 번역 (0.2.45 · design/35)."""

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


def _install_fake_gemini(monkeypatch: pytest.MonkeyPatch, calls: list[str], text: str = "촉매 활성.") -> None:
    """google.genai Client 를 프로세스에 심어 translate_en_to_ko 가 실 API 없이 돈다."""

    class _Models:
        def generate_content(self, **kwargs):  # noqa: ANN003
            calls.append(str(kwargs.get("contents") or ""))
            return SimpleNamespace(text=text, candidates=[])

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


def test_status_flags_translate() -> None:
    st = TestClient(app).get("/api/status").json()
    assert st["version"] == "0.2.45"
    assert "translate_en_ko" in st
    assert st["tab_close"] is True


def test_design_35_contract() -> None:
    design = (ROOT / "docs" / "design" / "35-translate-simple.md").read_text(
        encoding="utf-8"
    )
    assert "0.2.43" in design
    assert "asr.translate.v1" in design
    assert "/api/translate" in design
    assert "다단계" in design
    # Live Enable / IPS 는 Trading Gate — ASR 설계에서 명시적으로 제외
    assert "Live Enable" in design or "IPS" in design


def test_ui_wiring_contract() -> None:
    html = (ROOT / "src" / "sentence_reading" / "static" / "index.html").read_text(
        encoding="utf-8"
    )
    assert 'id="translateBtn"' in html
    assert 'id="sentenceKo"' in html
    js = (ROOT / "src" / "sentence_reading" / "static" / "app.js").read_text(
        encoding="utf-8"
    )
    assert "asr.translate.v1" in js
    assert "function loadTranslatePrefs" in js
    assert "function refreshSentenceKo" in js
    assert "/api/translate" in js
    assert "design/35" in js
    served = TestClient(app).get("/").text
    assert "app.js?v=0.2.45" in served


def test_empty_and_whitespace(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(tr, "gemini_api_key", lambda: "fake-key")
    assert tr.translate_en_to_ko("") == {"ok": False, "error": "empty"}
    assert tr.translate_en_to_ko("   \n\t  ") == {"ok": False, "error": "empty"}
    assert tr.translate_en_to_ko("<p></p>") == {"ok": False, "error": "empty"}


def test_too_long(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(tr, "gemini_api_key", lambda: "fake-key")
    huge = "a" * (tr._MAX_CHARS + 1)
    out = tr.translate_en_to_ko(huge)
    assert out["ok"] is False
    assert out["error"] == "too_long"
    assert out["max_chars"] == tr._MAX_CHARS


def test_plain_none_is_empty() -> None:
    assert tr._plain(None) == ""  # type: ignore[arg-type]
    assert tr._plain("<i>  x  </i>") == "x"


def test_gemini_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(tr, "gemini_api_key", lambda: "")
    out = tr.translate_en_to_ko("Hello world.")
    assert out == {"ok": False, "error": "gemini_unavailable"}


def test_strips_html_and_caches(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []
    _install_fake_gemini(monkeypatch, calls, text='  "촉매 활성."  ')

    r1 = tr.translate_en_to_ko("<b>Catalyst</b>  activity.")
    assert r1["ok"] is True
    assert r1["ko"] == "촉매 활성."
    assert r1["cached"] is False
    assert len(calls) == 1
    assert "Catalyst activity." in calls[0]
    assert "<b>" not in calls[0]

    r2 = tr.translate_en_to_ko("Catalyst activity.")
    assert r2["ok"] is True
    assert r2["ko"] == "촉매 활성."
    assert r2["cached"] is True
    assert len(calls) == 1


def test_translate_failed_empty_model(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []
    _install_fake_gemini(monkeypatch, calls, text="   ")
    out = tr.translate_en_to_ko("Something happened.")
    assert out == {"ok": False, "error": "translate_failed"}


def test_api_invalid_and_ok(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("sentence_reading.api.app.gemini_available", lambda: True)
    client = TestClient(app)

    bad = client.post("/api/translate", json={"text": 123})
    assert bad.json()["ok"] is False
    assert bad.json()["error"] == "invalid_text"

    monkeypatch.setattr(
        "sentence_reading.llm.translate.translate_dispatch",
        lambda t, m="pipeline": {"ok": False, "error": "empty"},
    )
    empty = client.post("/api/translate", json={"text": ""})
    assert empty.json()["error"] == "empty"

    monkeypatch.setattr(
        "sentence_reading.llm.translate.translate_dispatch",
        lambda t, m="pipeline": {
            "ok": True,
            "ko": "안녕",
            "cached": False,
            "mode": m,
            "stages_done": ["draft", "sense", "polish"],
        },
    )
    ok = client.post("/api/translate", json={"text": "Hi"})
    body = ok.json()
    assert body["ok"] is True
    assert body["ko"] == "안녕"
    assert body["source_lang"] == "en"
    assert body["target_lang"] == "ko"
    assert body["mode"] == "pipeline"


def test_api_gemini_gate(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "sentence_reading.api.app.gemini_available", lambda: False
    )
    r = TestClient(app).post("/api/translate", json={"text": "Hi"})
    assert r.json() == {"ok": False, "error": "gemini_unavailable"}


def test_api_exception_maps(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("sentence_reading.api.app.gemini_available", lambda: True)

    def boom(_t: str, _m: str = "pipeline") -> dict:
        raise RuntimeError("network down")

    monkeypatch.setattr(
        "sentence_reading.llm.translate.translate_dispatch", boom
    )
    r = TestClient(app).post("/api/translate", json={"text": "Hi"})
    body = r.json()
    assert body["ok"] is False
    assert body["error"] == "translate_failed"
    assert "network" in body.get("message", "")
