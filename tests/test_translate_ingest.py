"""첨부 시 섹션 번역 + 요지 재감수 (0.3.3 · design/40)."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from sentence_reading.api.app import app
from sentence_reading.cache import paper_cache as pc
from sentence_reading.llm import translate as tr
from sentence_reading.llm import translate_section as ts
from sentence_reading.models import Figure, PaperSession, Sentence

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def _clear_cache() -> None:
    tr.clear_translate_cache_for_tests()
    yield
    tr.clear_translate_cache_for_tests()


def test_status_ingest_translate_flag() -> None:
    st = TestClient(app).get("/api/status").json()
    assert st["version"] == "0.3.4"
    assert st["translate_ingest_sections"] is True
    assert st["translate_side_by_side"] is True


def test_design_40_contract() -> None:
    design = (ROOT / "docs" / "design" / "40-ingest-section-translate.md").read_text(
        encoding="utf-8"
    )
    assert "0.2.48" in design
    assert "text_ko" in design
    assert "caption_ko" in design
    assert "translate_digests" in design
    assert "harmonize" in design.lower() or "재감수" in design
    assert "Live Enable" in design or "IPS" in design
    assert "Flutter" in design


def test_ui_prefers_cached_ko() -> None:
    js = (ROOT / "src" / "sentence_reading" / "static" / "app.js").read_text(
        encoding="utf-8"
    )
    assert "text_ko" in js
    assert "caption_ko" in js
    assert "translateDigests" in js
    assert "번역 정리본" in js
    assert "design/40" in js
    css = (ROOT / "src" / "sentence_reading" / "static" / "styles.css").read_text(
        encoding="utf-8"
    )
    assert "section-review-digest" in css
    served = TestClient(app).get("/").text
    assert "app.js?v=0.3.4" in served
    assert "styles.css?v=0.3.4" in served


def test_public_dict_includes_ko_and_digests() -> None:
    session = PaperSession(
        title="T",
        figures=[
            Figure(
                id="f1",
                image_src="data:image/png;base64,aa",
                caption="Fig. 1",
                caption_ko="그림 1",
            )
        ],
        sentences=[
            Sentence(
                id="s1",
                text="Hello catalyst.",
                section="abstract",
                text_ko="안녕 촉매.",
            )
        ],
        translate_digests={"abstract": {"en": "Claim.", "ko": "주장."}},
    )
    data = session.to_public_dict()
    assert data["sentences"][0]["text_ko"] == "안녕 촉매."
    assert data["figures"][0]["caption_ko"] == "그림 1"
    assert data["translate_digests"]["abstract"]["ko"] == "주장."
    assert data["sentence"]["text_ko"] == "안녕 촉매."
    assert data["figure"]["caption_ko"] == "그림 1"


def test_cache_roundtrip_ko(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(pc, "cache_root", lambda: tmp_path)
    session = PaperSession(
        title="Cache Translate Paper Title Long Enough",
        figures=[
            Figure(
                id="f1",
                image_src="data:image/png;base64,iVBORw0KGgo=",
                caption="Fig. 1 scheme",
                caption_ko="그림 1 도식",
            )
        ],
        sentences=[
            Sentence(
                id="s1",
                text="Activity rose.",
                section="body",
                text_ko="활성이 올랐다.",
            )
        ],
        translate_digests={"body": {"en": "Activity rose.", "ko": "활성 상승."}},
    )
    entry = pc.save_paper_session(session, debone=True, source="pdf")
    loaded_pair = pc.load_cached_session(entry["id"])
    assert loaded_pair is not None
    loaded, _meta = loaded_pair
    assert loaded.sentences[0].text_ko == "활성이 올랐다."
    assert loaded.figures[0].caption_ko == "그림 1 도식"
    assert loaded.translate_digests["body"]["ko"] == "활성 상승."
    meta = (tmp_path / entry["id"] / "session.json").read_text(encoding="utf-8")
    assert "translate_doc_version" in meta
    assert "doc-v1" in meta


def test_enrich_no_gemini_passthrough(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ts, "gemini_api_key", lambda: "")
    sents = [Sentence(id="s1", text="Ni catalyst.", section="body")]
    figs = [Figure(id="f1", image_src="x", caption="Fig. 1")]
    out_s, out_f, dig, warn = ts.enrich_session_translations(sents, figs)
    assert out_s[0].text_ko == ""
    assert out_f[0].caption_ko == ""
    assert dig == {}
    assert "translate_skipped_no_gemini" in warn


def test_enrich_pipeline_and_digest(monkeypatch: pytest.MonkeyPatch) -> None:
    """정상 경로: pipeline → digest → harmonize (mock Gemini)."""

    def fake_dispatch(text: str, mode: str = "pipeline") -> dict:
        return {"ok": True, "ko": f"KO:{text[:40]}", "mode": mode}

    def fake_gen(system: str, user: str) -> str:
        if "theme summaries" in user or "EN:" in system or "summarize" in system.lower():
            return "EN: Theme claim.\nKO: 요지 주장."
        return "감수된 한국어"

    monkeypatch.setattr(ts, "gemini_api_key", lambda: "fake")
    monkeypatch.setattr(tr, "translate_dispatch", fake_dispatch)
    monkeypatch.setattr(tr, "_gemini_generate", fake_gen)

    sents = [
        Sentence(id="s1", text="Catalyst A works.", section="abstract"),
        Sentence(id="s2", text="We measured rates.", section="abstract"),
        Sentence(id="s3", text="Body claim here.", section="body"),
    ]
    figs = [Figure(id="f1", image_src="x", caption="Fig. 1 XRD peaks")]
    out_s, out_f, dig, warn = ts.enrich_session_translations(sents, figs)
    assert out_s[0].text_ko == "감수된 한국어"
    assert out_s[2].text_ko == "감수된 한국어"
    assert dig["abstract"]["ko"] == "요지 주장."
    assert dig["body"]["en"] == "Theme claim."
    assert out_f[0].caption_ko == "감수된 한국어"
    assert warn == [] or "translate_empty" not in warn


def test_enrich_edge_empty_and_garbage(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ts, "gemini_api_key", lambda: "fake")
    monkeypatch.setattr(ts, "_pipeline_staged", lambda text, on_stage=None: None)
    monkeypatch.setattr(tr, "_gemini_generate", lambda system, user: "!!!not a digest!!!")

    sents = [
        Sentence(id="s0", text="   ", section="body"),
        Sentence(id="s1", text="<b></b>", section=""),
        Sentence(id="s2", text="Only real sentence.", section="body"),
    ]
    figs = [
        Figure(id="f0", image_src="x", caption=""),
        Figure(id="f1", image_src="x", caption="   "),
    ]
    out_s, out_f, dig, warn = ts.enrich_session_translations(sents, figs)
    assert out_s[0].text_ko == ""
    assert out_s[2].text_ko == ""
    assert dig.get("body", {}).get("ko") == "!!!not a digest!!!"
    assert all(f.caption_ko == "" for f in out_f)
    assert "translate_empty" in warn


def test_parse_digest_variants() -> None:
    assert ts._parse_digest("EN: Hello.\nKO: 안녕.") == {
        "en": "Hello.",
        "ko": "안녕.",
    }
    assert ts._parse_digest("") == {"en": "", "ko": ""}
    assert ts._parse_digest("only ko blob")["ko"] == "only ko blob"
    # 말도 안 되는 키/값
    assert ts.digest_public(None) == {}
    assert ts.digest_public({"x": "nope"}) == {}
    assert ts.digest_public({"a": {"en": 1, "ko": None}})["a"] == {
        "en": "1",
        "ko": "",
    }


def test_ingest_stage_mentions_translate() -> None:
    src = (ROOT / "src" / "sentence_reading" / "api" / "app.py").read_text(
        encoding="utf-8"
    )
    assert "enrich_session_translations" in src
    assert 'stage="translate"' in src
    assert "translate_digests=digests" in src
