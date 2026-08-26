"""섹션 번역 진행 콜백 (0.3.3 · design/43)."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from sentence_reading.api.app import app
from sentence_reading.llm import translate as tr
from sentence_reading.llm import translate_section as ts
from sentence_reading.models import Figure, Sentence

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def _clear_cache() -> None:
    tr.clear_translate_cache_for_tests()
    yield
    tr.clear_translate_cache_for_tests()


def test_status_version() -> None:
    st = TestClient(app).get("/api/status").json()
    assert st["version"] == "0.3.62"


def test_design_43_contract() -> None:
    design = (ROOT / "docs" / "design" / "43-translate-progress.md").read_text(
        encoding="utf-8"
    )
    assert "0.2.51" in design
    assert "on_progress" in design
    assert "초록 번역" in design or "번역" in design
    assert "재감수" in design
    assert "캡션" in design
    assert "Live Enable" in design or "IPS" in design


def test_sec_label_ko() -> None:
    assert ts._sec_label("abstract") == "초록"
    assert ts._sec_label("body") == "본문"
    assert ts._sec_label("weird_sec") == "weird_sec"


def test_on_progress_messages_and_fractions(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "test-key-not-real")

    def fake_pipeline(text: str, on_stage=None) -> str:
        ko = f"KO:{text[:20]}"
        if on_stage:
            on_stage(ko, "polish")
        return ko

    def fake_digest(section: str, lines: list[str]) -> dict[str, str]:
        return {"en": f"theme {section}", "ko": f"요지 {section}"}

    def fake_harm(en: str, ko: str, digest: dict[str, str]) -> str:
        return ko + "|h"

    monkeypatch.setattr(ts, "_pipeline_staged", fake_pipeline)
    monkeypatch.setattr(ts, "_make_digest", fake_digest)
    monkeypatch.setattr(ts, "_harmonize", fake_harm)
    monkeypatch.setattr(ts, "gemini_api_key", lambda: "test-key-not-real")

    events: list[tuple[str, float]] = []

    def on_progress(msg: str, frac: float) -> None:
        events.append((msg, frac))

    sentences = [
        Sentence(id="s1", text="First claim about Ni.", section="abstract"),
        Sentence(id="s2", text="Second claim about Fe.", section="abstract"),
        Sentence(id="s3", text="Body sentence here.", section="body"),
    ]
    figures = [
        Figure(id="f1", image_src="data:image/png;base64,aa", caption="Fig. 1 XRD"),
    ]

    out_s, out_f, digests, warnings = ts.enrich_session_translations(
        sentences, figures, on_progress=on_progress
    )
    assert not warnings
    assert digests["abstract"]["ko"]
    assert out_s[0].text_ko.startswith("KO:")
    assert "|h" in out_s[0].text_ko
    assert out_f[0].caption_ko.startswith("KO:")

    msgs = [m for m, _ in events]
    assert any(m.startswith("초록 번역 ") for m in msgs)
    assert "초록 요지 정리" in msgs
    assert any(m.startswith("초록 재감수 ") for m in msgs)
    assert any(m.startswith("본문 번역 ") for m in msgs)
    assert any(m.startswith("캡션 ") for m in msgs)

    # fraction 단조 증가·마지막 1.0 근처
    fracs = [f for _, f in events]
    assert fracs[0] > 0
    assert fracs[-1] >= 0.99
    assert all(0 < f <= 1.0 for f in fracs)


def test_on_progress_exception_fail_soft(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "test-key-not-real")

    def fake_pipeline(text: str, on_stage=None) -> str:
        if on_stage:
            on_stage("한", "polish")
        return "한"

    monkeypatch.setattr(ts, "_pipeline_staged", fake_pipeline)
    monkeypatch.setattr(
        ts, "_make_digest", lambda sec, lines: {"en": "e", "ko": "k"}
    )
    monkeypatch.setattr(ts, "_harmonize", lambda en, ko, d: ko)
    monkeypatch.setattr(ts, "gemini_api_key", lambda: "test-key-not-real")

    def boom(_msg: str, _frac: float) -> None:
        raise RuntimeError("badge broken")

    sentences = [Sentence(id="s1", text="Hello.", section="abstract")]
    out_s, _out_f, _d, warnings = ts.enrich_session_translations(
        sentences, [], on_progress=boom
    )
    assert not warnings
    assert out_s[0].text_ko == "한"


def test_estimate_units_empty() -> None:
    by_sec: dict[str, list[int]] = {"abstract": [0]}
    sents = [Sentence(id="s1", text="   ", section="abstract")]
    assert ts._estimate_progress_units(sents, [], by_sec) == 1


def test_app_wires_on_progress() -> None:
    src = (ROOT / "src" / "sentence_reading" / "api" / "app.py").read_text(
        encoding="utf-8"
    )
    assert "on_progress=_tr_progress" in src
    assert "on_progress=_bf_progress" in src
    assert "design/43" in src
