"""Progressive 읽기 열기 (0.3.3 · design/45)."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from sentence_reading.api import app as app_mod
from sentence_reading.api.app import app
from sentence_reading.llm import translate as tr
from sentence_reading.llm import translate_section as ts
from sentence_reading.models import Figure, PaperSession, Sentence

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def _clear_cache() -> None:
    tr.clear_translate_cache_for_tests()
    yield
    tr.clear_translate_cache_for_tests()


def test_status_progressive_flag() -> None:
    st = TestClient(app).get("/api/status").json()
    assert st["version"] == "0.3.25"
    assert st["translate_progressive"] is True
    assert st["translate_live_fallback"] is False
    assert st["compound_figures"] is False


def test_design_45_contract() -> None:
    design = (ROOT / "docs" / "design" / "45-progressive-translate.md").read_text(
        encoding="utf-8"
    )
    assert "0.2.53" in design
    assert "text_ko_stage" in design
    assert "번역 진행 중" in design
    assert "Live Enable" in design or "IPS" in design
    assert "Trading Gate" in design or "ASR 밖" in design


def test_public_dict_includes_stages() -> None:
    session = PaperSession(
        title="T",
        sentences=[
            Sentence(
                id="s1",
                text="Hello.",
                section="abstract",
                text_ko="안녕.",
                text_ko_stage="draft",
            )
        ],
        figures=[
            Figure(
                id="f1",
                image_src="data:image/png;base64,aa",
                caption="Fig. 1",
                caption_ko="그림 1",
                caption_ko_stage="polish",
            )
        ],
    )
    d = session.to_public_dict()
    assert d["sentences"][0]["text_ko_stage"] == "draft"
    assert d["figures"][0]["caption_ko_stage"] == "polish"
    assert d["sentence"]["text_ko_stage"] == "draft"


def test_needs_backfill_incomplete_stage() -> None:
    sents = [
        Sentence(
            id="s1",
            text="Catalyst works.",
            section="abstract",
            text_ko="촉매가 작동한다.",
            text_ko_stage="draft",
        )
    ]
    assert ts.needs_translate_backfill(sents, []) is True


def test_needs_backfill_final_ok() -> None:
    sents = [
        Sentence(
            id="s1",
            text="Catalyst works.",
            section="abstract",
            text_ko="촉매가 작동한다.",
            text_ko_stage="harmonize",
        )
    ]
    digests = {"abstract": {"en": "x", "ko": "y"}}
    assert ts.needs_translate_backfill(sents, [], digests) is False


def test_needs_backfill_edge_empty() -> None:
    assert ts.needs_translate_backfill([], []) is False
    assert ts.needs_translate_backfill(
        [Sentence(id="s", text="   ", section="body")], []
    ) is False


def test_pipeline_staged_emits_stages(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ts, "gemini_api_key", lambda: "k")
    monkeypatch.setattr(tr, "_cache_get", lambda _k: None)
    monkeypatch.setattr(tr, "_cache_put", lambda _k, _v: None)
    calls = {"n": 0}

    def fake_gen(system: str, user: str) -> str:
        calls["n"] += 1
        if "terminology" in user.lower() or "Revise for terminology" in user:
            return "용어수정"
        if "Polish" in user or "readability" in user.lower():
            return "윤문"
        return "초벌"

    monkeypatch.setattr(tr, "_gemini_generate", fake_gen)
    events: list[tuple[str, str]] = []

    out = ts._pipeline_staged("Ni catalyst.", on_stage=lambda ko, st: events.append((ko, st)))
    assert out == "윤문"
    assert [e[1] for e in events] == ["draft", "sense", "polish"]


def test_job_publish_partial_and_status() -> None:
    jid = "job_test_partial"
    app_mod._JOBS[jid] = {
        "percent": 10,
        "stage": "extract",
        "message": "",
        "done": False,
    }
    app_mod._job_publish_partial(
        jid,
        {
            "session_id": "ses_x",
            "sentences": [{"id": "s1", "text": "Hi", "text_ko": "", "section": "body"}],
            "figures": [],
            "title": "T",
        },
        message="읽기 가능 · 번역 중",
    )
    st = TestClient(app).get(f"/api/ingest/jobs/{jid}").json()
    assert st["done"] is False
    assert st["translate_pending"] is True
    assert st["session_id"] == "ses_x"
    assert st["message"] == "읽기 가능 · 번역 중"
    del app_mod._JOBS[jid]


def test_ui_progressive_contracts() -> None:
    js = (ROOT / "src" / "sentence_reading" / "static" / "app.js").read_text(
        encoding="utf-8"
    )
    assert "번역 진행 중" in js
    assert "mergeTranslateProgress" in js
    assert "frozenKoSentenceId" in js
    assert "translate_pending" in js
    assert "design/45" in js
    served = TestClient(app).get("/").text
    assert "app.js?v=0.3.25" in served
