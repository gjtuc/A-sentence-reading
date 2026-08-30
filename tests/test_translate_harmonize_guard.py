"""harmonize text_ko 가드 — 영어 메타 추론 누출 방지 (0.3.91)."""

from __future__ import annotations

import pytest

from sentence_reading.llm import translate as tr
from sentence_reading.llm import translate_section as ts
from sentence_reading.models import Figure, Sentence

_DIRTY_SENTENCE_71 = (
    'Ni-Cu 합금 형성을 확인했다. '
    "Let's re-evaluate. The theme says \"XRD... confirmed the formation of Ni-Cu alloys\". "
    'The source says "The sintering of metal nanoparticles..."'
)

_CLEAN_KO = (
    "금속 나노입자의 소결은 촉매 활성에 중요한 역할을 하며, "
    "Ni-Cu 합금의 형성이 XRD로 확인되었다."
)


def test_is_dirty_ko_detects_sentence_71_meta() -> None:
    assert tr.is_dirty_ko_output(_DIRTY_SENTENCE_71) is True


def test_is_dirty_ko_accepts_pure_korean() -> None:
    assert tr.is_dirty_ko_output(_CLEAN_KO) is False


def test_is_dirty_ko_accepts_latin_formula_in_korean() -> None:
    ko = "Ni/Cu 비율을 조절하면 CO2 환원 활성이 향상된다."
    assert tr.is_dirty_ko_output(ko) is False


def test_sanitize_ko_strips_prefix() -> None:
    assert tr.sanitize_ko_output('Korean: 안녕하세요') == "안녕하세요"


def test_harmonize_rejects_dirty_returns_draft(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ts, "gemini_api_key", lambda: "fake")

    def dirty_gen(system: str, user: str) -> str:
        return _DIRTY_SENTENCE_71

    monkeypatch.setattr(tr, "_gemini_generate", dirty_gen)
    draft = "금속 나노입자의 소결이 중요하다."
    ko, accepted = ts._harmonize("The sintering of metal nanoparticles.", draft, {"en": "e", "ko": "k"})
    assert ko == draft
    assert accepted is False


def test_harmonize_accepts_clean_korean(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ts, "gemini_api_key", lambda: "fake")
    monkeypatch.setattr(tr, "_gemini_generate", lambda s, u: _CLEAN_KO)
    draft = "초안 번역."
    ko, accepted = ts._harmonize("Source.", draft, {"en": "e", "ko": "k"})
    assert ko == _CLEAN_KO
    assert accepted is True


def test_enrich_keeps_draft_when_harmonize_dirty(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ASR_TRANSLATE_BACKEND", "gemini")
    monkeypatch.setattr(ts, "gemini_api_key", lambda: "fake")

    def fake_pipeline(text: str, on_stage=None) -> str:
        ko = "금속 나노입자의 소결이 중요하다."
        if on_stage:
            on_stage(ko, "polish")
        return ko

    def dirty_harm(en: str, ko: str, digest: dict[str, str]) -> tuple[str, bool]:
        return ko, False

    monkeypatch.setattr(ts, "_pipeline_staged", fake_pipeline)
    monkeypatch.setattr(ts, "_make_digest", lambda sec, lines: {"en": "e", "ko": "k"})
    monkeypatch.setattr(ts, "_harmonize", dirty_harm)

    sents = [Sentence(id="s1", text="The sintering of metal nanoparticles.", section="body")]
    out_s, _f, _d, _w = ts.enrich_session_translations(sents, [])
    assert out_s[0].text_ko == "금속 나노입자의 소결이 중요하다."
    assert out_s[0].text_ko_stage == "polish"


def test_enrich_harmonize_stage_on_clean(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ASR_TRANSLATE_BACKEND", "gemini")
    monkeypatch.setattr(ts, "gemini_api_key", lambda: "fake")

    def fake_pipeline(text: str, on_stage=None) -> str:
        ko = "초안."
        if on_stage:
            on_stage(ko, "polish")
        return ko

    def clean_harm(en: str, ko: str, digest: dict[str, str]) -> tuple[str, bool]:
        return "감수된 한국어.", True

    monkeypatch.setattr(ts, "_pipeline_staged", fake_pipeline)
    monkeypatch.setattr(ts, "_make_digest", lambda sec, lines: {"en": "e", "ko": "k"})
    monkeypatch.setattr(ts, "_harmonize", clean_harm)

    sents = [Sentence(id="s1", text="Hello.", section="body")]
    out_s, _f, _d, _w = ts.enrich_session_translations(sents, [])
    assert out_s[0].text_ko == "감수된 한국어."
    assert out_s[0].text_ko_stage == "harmonize"


def test_needs_translate_backfill_dirty_harmonize() -> None:
    sents = [
        Sentence(
            id="s1",
            text="The sintering of metal nanoparticles.",
            text_ko=_DIRTY_SENTENCE_71,
            text_ko_stage="harmonize",
            section="body",
        )
    ]
    assert ts.needs_translate_backfill(sents, []) is True


def test_needs_translate_backfill_dirty_caption() -> None:
    figs = [
        Figure(
            id="f1",
            image_src="x",
            caption="Fig. 1",
            caption_ko=_DIRTY_SENTENCE_71,
            caption_ko_stage="harmonize",
        )
    ]
    assert ts.needs_translate_backfill([], figs) is True


def test_needs_translate_backfill_clean_harmonize_false() -> None:
    sents = [
        Sentence(
            id="s1",
            text="Hello.",
            text_ko=_CLEAN_KO,
            text_ko_stage="harmonize",
            section="body",
        )
    ]
    assert ts.needs_translate_backfill(sents, []) is False
