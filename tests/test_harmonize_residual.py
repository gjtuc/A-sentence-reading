"""design/169o — enrich run_harmonize flag + residual helpers."""

from __future__ import annotations

from sentence_reading.llm import translate_section as ts
from sentence_reading.models import Figure, Sentence


def test_count_harmonize_targets_skips_done_and_missing_digest() -> None:
    sents = [
        Sentence(id="1", text="Hello world.", section="abstract", text_ko="안녕", text_ko_stage="google"),
        Sentence(id="2", text="Second.", section="abstract", text_ko="둘", text_ko_stage="harmonize"),
        Sentence(id="3", text="No digest sec.", section="body", text_ko="초안", text_ko_stage="google"),
    ]
    figs = [
        Figure(id="f1", image_src="", caption="Cap one.", caption_ko="캡션", caption_ko_stage="google"),
    ]
    digests = {"abstract": {"en": "theme", "ko": "요지"}}
    # body missing → sentence in body skipped; caption uses any nonempty digest
    assert ts.count_harmonize_targets(sents, figs, digests) == 2
    digests["body"] = {"en": "body", "ko": "본문"}
    # body sentence now eligible too
    assert ts.count_harmonize_targets(sents, figs, digests) == 3


def test_enrich_run_harmonize_false_skips_harmonize(monkeypatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "test-key-not-real")
    monkeypatch.setenv("ASR_TRANSLATE_BACKEND", "gemini")
    monkeypatch.setattr(
        "sentence_reading.llm.translate_google.google_translate_available",
        lambda: False,
    )
    harm_calls: list[str] = []

    def fake_pipeline(text: str, on_stage=None) -> str:
        ko = f"KO:{text[:12]}"
        if on_stage:
            on_stage(ko, "polish")
        return ko

    def fake_digest(section: str, lines: list[str]) -> dict[str, str]:
        return {"en": f"theme {section}", "ko": f"요지 {section}"}

    def fake_harm(en: str, ko: str, digest: dict[str, str]) -> tuple[str, bool]:
        harm_calls.append(en[:20])
        return ko + "|h", True

    monkeypatch.setattr(ts, "_pipeline_staged", fake_pipeline)
    monkeypatch.setattr(ts, "_make_digest", fake_digest)
    monkeypatch.setattr(ts, "_harmonize", fake_harm)
    monkeypatch.setattr(ts, "gemini_api_key", lambda: "test-key-not-real")

    sents = [
        Sentence(id="1", text="Alpha sentence here.", section="abstract"),
        Sentence(id="2", text="Beta sentence here.", section="abstract"),
    ]
    figs: list[Figure] = []
    new_s, new_f, digests, warnings = ts.enrich_session_translations(
        sents, figs, run_harmonize=False
    )
    assert not warnings or "translate_empty" not in warnings
    assert digests.get("abstract", {}).get("en")
    assert all(s.text_ko for s in new_s)
    assert all((s.text_ko_stage or "") != "harmonize" for s in new_s)
    assert harm_calls == []


def test_harmonize_session_residual_calls_harmonize(monkeypatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "test-key-not-real")
    harm_n = {"n": 0}

    def fake_harm(en: str, ko: str, digest: dict[str, str]) -> tuple[str, bool]:
        harm_n["n"] += 1
        return ko + "|h", True

    monkeypatch.setattr(ts, "_harmonize", fake_harm)
    monkeypatch.setattr(ts, "gemini_api_key", lambda: "test-key-not-real")

    sents = [
        Sentence(
            id="1",
            text="Alpha sentence here.",
            section="abstract",
            text_ko="초안A",
            text_ko_stage="google",
        ),
        Sentence(
            id="2",
            text="Beta sentence here.",
            section="abstract",
            text_ko="초안B",
            text_ko_stage="google",
        ),
    ]
    digests = {"abstract": {"en": "t", "ko": "요"}}
    items: list[tuple[str, int, str]] = []

    def on_item(kind: str, index: int, ko: str, stage: str) -> None:
        items.append((kind, index, stage))

    out_s, _out_f, warn = ts.harmonize_session_residual(
        sents, [], digests, on_item=on_item
    )
    assert warn == []
    assert harm_n["n"] == 2
    assert all(s.text_ko_stage == "harmonize" for s in out_s)
    assert all(stage == "harmonize" for _, _, stage in items)
