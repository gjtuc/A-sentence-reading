"""Google bulk 번역 + Gemini 후처리 (design/153)."""

from __future__ import annotations

import pytest

from sentence_reading.llm import translate as tr
from sentence_reading.llm import translate_google as tg
from sentence_reading.llm import translate_section as ts
from sentence_reading.models import Figure, Sentence


@pytest.fixture(autouse=True)
def _clear_caches() -> None:
    tr.clear_translate_cache_for_tests()
    tg.clear_google_translate_client_for_tests()
    yield
    tr.clear_translate_cache_for_tests()
    tg.clear_google_translate_client_for_tests()


def test_google_batch_preserves_order(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[list[str]] = []

    def fake_batch(texts: list[str]) -> list[str | None]:
        seen.append(list(texts))
        return [f"KO:{t}" for t in texts]

    monkeypatch.setattr(tg, "translate_batch_en_to_ko", fake_batch)
    out = tg.translate_batch_en_to_ko(["A", "B"])
    assert out == ["KO:A", "KO:B"]
    assert seen == [["A", "B"]]


def test_simple_uses_google(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ASR_TRANSLATE_BACKEND", "google")
    monkeypatch.setattr(tg, "google_translate_available", lambda: True)
    monkeypatch.setattr(tg, "translate_one_en_to_ko", lambda t: f"번역:{t}")
    monkeypatch.setattr(tr, "gemini_api_key", lambda: "")

    out = tr.translate_en_to_ko("Catalyst works.")
    assert out["ok"] is True
    assert out["ko"] == "번역:Catalyst works."
    assert out["stages_done"] == ["google"]


def test_pipeline_google_plus_gemini_post(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ASR_TRANSLATE_BACKEND", "google")
    monkeypatch.setenv("ASR_TRANSLATE_GEMINI_POST", "1")
    monkeypatch.setattr(tg, "google_translate_available", lambda: True)
    monkeypatch.setattr(tg, "translate_one_en_to_ko", lambda t: "초안")
    monkeypatch.setattr(tr, "gemini_api_key", lambda: "fake")
    monkeypatch.setattr(
        tr,
        "_gemini_refine",
        lambda en, ko, sense=True, polish=True: ("윤문", ["sense", "polish"]),
    )

    out = tr.translate_en_to_ko_pipeline("Ni catalyst.")
    assert out["ok"] is True
    assert out["ko"] == "윤문"
    assert out["stages_done"] == ["google", "sense", "polish"]


def test_enrich_google_bulk_then_harmonize(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ASR_TRANSLATE_BACKEND", "google")

    def fake_batch(texts: list[str]) -> list[str | None]:
        return [f"G:{t[:20]}" for t in texts]

    def fake_gen(system: str, user: str) -> str:
        if "theme summaries" in user or "summarize" in system.lower():
            return "EN: Theme.\nKO: 요지."
        return "감수됨"

    monkeypatch.setattr(tg, "google_translate_available", lambda: True)
    monkeypatch.setattr(tg, "translate_batch_en_to_ko", fake_batch)
    monkeypatch.setattr(ts, "gemini_api_key", lambda: "fake")
    monkeypatch.setattr(tr, "_gemini_generate", fake_gen)

    sents = [
        Sentence(id="s1", text="Catalyst A.", section="abstract"),
        Sentence(id="s2", text="Rate up.", section="abstract"),
    ]
    figs = [Figure(id="f1", image_src="x", caption="Fig. 1")]
    out_s, out_f, dig, warn = ts.enrich_session_translations(sents, figs)
    assert out_s[0].text_ko == "감수됨"
    assert out_s[0].text_ko_stage == "harmonize"
    assert dig["abstract"]["ko"] == "요지."
    assert out_f[0].caption_ko == "감수됨"
    assert "translate_empty" not in warn


def test_enrich_google_only_no_post(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ASR_TRANSLATE_BACKEND", "google")
    monkeypatch.setenv("ASR_TRANSLATE_GEMINI_POST", "0")

    monkeypatch.setattr(
        tg,
        "translate_batch_en_to_ko",
        lambda texts: [f"G:{t}" for t in texts],
    )
    monkeypatch.setattr(tg, "google_translate_available", lambda: True)
    monkeypatch.setattr(ts, "gemini_api_key", lambda: "")

    sents = [Sentence(id="s1", text="Hello.", section="body")]
    out_s, _out_f, dig, warn = ts.enrich_session_translations(sents, [])
    assert out_s[0].text_ko == "G:Hello."
    assert out_s[0].text_ko_stage == "google"
    assert dig.get("body") == {"en": "", "ko": ""}
    assert warn == []
