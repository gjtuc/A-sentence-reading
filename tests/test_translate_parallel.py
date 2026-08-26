"""번역 문장 병렬 (0.2.54 · design/46; 앱 버전은 후속 범프와 무관)."""

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


def test_status_parallel_flag() -> None:
    st = TestClient(app).get("/api/status").json()
    assert st["version"] == "0.3.61"
    assert st["translate_parallel"] is True
    assert 1 <= int(st["translate_workers"]) <= 8


def test_design_46_contract() -> None:
    design = (ROOT / "docs" / "design" / "46-translate-parallel.md").read_text(
        encoding="utf-8"
    )
    assert "0.2.54" in design
    assert "ThreadPoolExecutor" in design or "동시" in design
    assert "ASR_TRANSLATE_WORKERS" in design
    assert "Live Enable" in design or "IPS" in design
    assert "Trading Gate" in design or "ASR 밖" in design


def test_worker_count_clamp(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ASR_TRANSLATE_WORKERS", raising=False)
    assert ts.translate_worker_count() == 4
    monkeypatch.setenv("ASR_TRANSLATE_WORKERS", "0")
    assert ts.translate_worker_count() == 1
    monkeypatch.setenv("ASR_TRANSLATE_WORKERS", "99")
    assert ts.translate_worker_count() == 8
    monkeypatch.setenv("ASR_TRANSLATE_WORKERS", "nope")
    assert ts.translate_worker_count() == 4
    monkeypatch.setenv("ASR_TRANSLATE_WORKERS", "6")
    assert ts.translate_worker_count() == 6


def test_parallel_enrich_with_workers(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ts, "gemini_api_key", lambda: "k")

    def fake_pipeline(text: str, on_stage=None) -> str:
        ko = f"KO:{text[:12]}"
        if on_stage:
            on_stage(ko, "polish")
        return ko

    monkeypatch.setattr(ts, "_pipeline_staged", fake_pipeline)
    monkeypatch.setattr(
        ts, "_make_digest", lambda sec, lines: {"en": "e", "ko": "k"}
    )
    monkeypatch.setattr(ts, "_harmonize", lambda en, ko, d: ko + "|h")

    sents = [
        Sentence(id=f"s{i}", text=f"Sentence number {i} about Ni.", section="abstract")
        for i in range(6)
    ]
    figs = [
        Figure(id="f1", image_src="data:image/png;base64,aa", caption="Fig. 1 a"),
        Figure(id="f2", image_src="data:image/png;base64,bb", caption="Fig. 2 b"),
    ]
    events: list[str] = []

    out_s, out_f, dig, warn = ts.enrich_session_translations(
        sents,
        figs,
        workers=3,
        on_progress=lambda m, f: events.append(m),
    )
    assert not warn
    assert all(s.text_ko.startswith("KO:") for s in out_s)
    assert all("|h" in s.text_ko for s in out_s)
    assert dig["abstract"]["ko"] == "k"
    assert all(f.caption_ko.startswith("KO:") for f in out_f)
    assert any(m.startswith("초록 번역 ") for m in events)
    assert "초록 요지 정리" in events
    assert any(m.startswith("캡션 ") for m in events)


def test_parallel_workers_one_matches_serial_shape(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(ts, "gemini_api_key", lambda: "k")
    monkeypatch.setattr(
        ts,
        "_pipeline_staged",
        lambda text, on_stage=None: (
            on_stage("한", "polish") if on_stage else None,
            "한",
        )[1],
    )
    monkeypatch.setattr(
        ts, "_make_digest", lambda sec, lines: {"en": "e", "ko": "k"}
    )
    monkeypatch.setattr(ts, "_harmonize", lambda en, ko, d: ko)

    sents = [Sentence(id="s1", text="Hello world.", section="body")]
    out_s, _f, _d, w = ts.enrich_session_translations(sents, [], workers=1)
    assert not w
    assert out_s[0].text_ko == "한"
    assert out_s[0].text_ko_stage == "harmonize"


def test_asset_version() -> None:
    served = TestClient(app).get("/").text
    assert "app.js?v=0.3.61" in served
