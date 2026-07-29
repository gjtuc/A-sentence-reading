"""브라우저 STT 발음 연습 · 단어 diff (0.2.53 · design/37)."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from sentence_reading.api.app import app
from sentence_reading.stt.compare import diff_tokens, normalize_en, tokenize_en

ROOT = Path(__file__).resolve().parents[1]


def test_status_stt_browser() -> None:
    st = TestClient(app).get("/api/status").json()
    assert st["version"] == "0.2.53"
    assert st["stt_browser"] is True
    assert st["translate_pipeline"] is True


def test_design_37_contract() -> None:
    design = (ROOT / "docs" / "design" / "37-stt-browser.md").read_text(
        encoding="utf-8"
    )
    assert "0.2.45" in design
    assert "점수" in design
    assert "/api/stt/compare" in design
    assert "Live Enable" in design or "IPS" in design
    assert "score" in design.lower()  # 금지 언급


def test_ui_assets_contract() -> None:
    html = (ROOT / "src" / "sentence_reading" / "static" / "index.html").read_text(
        encoding="utf-8"
    )
    assert 'id="sttPracticeBtn"' in html
    assert "stt_practice.js" in html
    js = (ROOT / "src" / "sentence_reading" / "static" / "stt_practice.js").read_text(
        encoding="utf-8"
    )
    assert "SpeechRecognition" in js or "webkitSpeechRecognition" in js
    assert "score" not in js.lower() or "점수 없음" in js
    # 채점 필드 생성 금지
    assert "accuracy" not in js.lower()
    assert "grade" not in js.lower()
    app_js = (ROOT / "src" / "sentence_reading" / "static" / "app.js").read_text(
        encoding="utf-8"
    )
    assert "design/37" in app_js
    assert "AsrSttPractice" in app_js
    served = TestClient(app).get("/").text
    assert "stt_practice.js?v=0.2.53" in served
    assert "app.js?v=0.2.53" in served


def test_normalize_and_tokenize_edges() -> None:
    assert normalize_en(None) == ""
    assert normalize_en("  <b>Hello,</b>  WORLD!  ") == "hello world"
    assert normalize_en("It's fine.") == "it's fine"
    assert tokenize_en("") == []
    assert tokenize_en("One  two") == ["one", "two"]


def test_diff_perfect_match() -> None:
    out = diff_tokens("The catalyst was active.", "the catalyst was active")
    assert out["ok"] is True
    assert all(d["op"] == "equal" for d in out["diff"])
    assert "score" not in out
    assert "grade" not in out
    assert "accuracy" not in out


def test_diff_replace_delete_insert() -> None:
    out = diff_tokens("the cat sat", "the dog sat down")
    assert out["ok"] is True
    ops = [d["op"] for d in out["diff"]]
    assert "replace" in ops or "delete" in ops
    assert "insert" in ops or "replace" in ops
    texts = out["diff"]
    assert any(d.get("heard") == "down" for d in texts if d["op"] in ("insert", "replace"))


def test_diff_empty_and_invalid() -> None:
    assert diff_tokens("", "")["error"] == "empty"
    assert diff_tokens("   ", "\n")["error"] == "empty"
    assert diff_tokens(123, "a")["error"] == "invalid_expected"  # type: ignore[arg-type]
    assert diff_tokens("a", [])["error"] == "invalid_heard"  # type: ignore[arg-type]


def test_diff_heard_only_inserts() -> None:
    out = diff_tokens("", "hello there")
    assert out["ok"] is True
    assert all(d["op"] == "insert" for d in out["diff"])


def test_diff_expected_only_deletes() -> None:
    out = diff_tokens("hello there", "")
    assert out["ok"] is True
    assert all(d["op"] == "delete" for d in out["diff"])


def test_api_compare_roundtrip() -> None:
    client = TestClient(app)
    r = client.post(
        "/api/stt/compare",
        json={"expected": "Catalyst activity.", "heard": "catalyst activity"},
    )
    body = r.json()
    assert body["ok"] is True
    assert "score" not in body
    assert body["diff"]

    bad = client.post("/api/stt/compare", json={"expected": 1, "heard": "x"})
    assert bad.json()["error"] == "invalid_expected"

    empty = client.post("/api/stt/compare", json={"expected": "", "heard": ""})
    assert empty.json()["error"] == "empty"
