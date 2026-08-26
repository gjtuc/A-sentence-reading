"""design/129 — lazy figure open (stubs + ±1 window)."""

from __future__ import annotations

import base64
from pathlib import Path

import fitz
from fastapi.testclient import TestClient

from sentence_reading.api import app as app_mod
from sentence_reading.api.app import app
from sentence_reading.cache import paper_cache as pc
from sentence_reading.models import Figure, PaperSession, Sentence

ROOT = Path(__file__).resolve().parents[1]
DESIGN = ROOT / "docs" / "design" / "129-lazy-figure-open.md"


def test_design_and_status_pin() -> None:
    assert DESIGN.is_file()
    st = TestClient(app).get("/api/status").json()
    assert st["version"] == "0.3.66"
    assert st.get("lazy_figure_open") is True
    assert "rich-v15" in str(st.get("pipeline_version") or "")


def test_open_omits_image_bytes(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("ASR_LOGIN_REQUIRED", "0")
    monkeypatch.setenv("ASR_ACCESS_GATE", "0")
    monkeypatch.setattr(pc, "cache_root", lambda: tmp_path)
    # Minimal paper on disk with a fat PNG.
    cid = "abcd1234ef"
    paper = tmp_path / cid
    figs = paper / "figures"
    figs.mkdir(parents=True)
    doc = fitz.open()
    page = doc.new_page(width=200, height=80)
    page.insert_text((10, 40), "Table 1 wide", fontsize=20)
    pix = page.get_pixmap(matrix=fitz.Matrix(4, 4))
    png = figs / "fig-0001.png"
    png.write_bytes(pix.tobytes("png"))
    doc.close()
    assert png.stat().st_size > 500
    session = {
        "title": "Lazy open fixture",
        "pipeline_version": "rich-v15",
        "sentences": [{"id": "s1", "text": "Hello world sentence."}],
        "figures": [
            {"id": "fig-0001", "caption": "Table 1. Metrics", "file": "figures/fig-0001.png"}
        ],
        "figure_index": 0,
        "sentence_index": 0,
    }
    import json

    (paper / "session.json").write_text(json.dumps(session), encoding="utf-8")

    # Bypass GCS refresh so unit test stays local.
    monkeypatch.setattr(
        "sentence_reading.llm.papers_gcs.refresh_paper_for_open",
        lambda _cid: (True, "ok"),
    )
    monkeypatch.setattr(
        "sentence_reading.llm.papers_gcs.paper_open_require_sentences",
        lambda: True,
    )

    client = TestClient(app)
    res = client.post(f"/api/cache/papers/{cid}/open", json={})
    assert res.status_code == 200, res.text
    data = res.json()
    assert data.get("ok") is True
    assert data.get("lazy_figures") is True
    assert data["sentence_count"] == 1
    assert data["figure_count"] == 1
    assert data["figures"][0]["caption"].startswith("Table 1")
    # WHY: open must not ship the PNG (regression = timeout class).
    assert (data["figures"][0].get("image_src") or "") == ""
    assert len(res.content) < 50_000

    sid = data["session_id"]
    win = client.get(f"/api/session/{sid}/figures/window", params={"center": 0, "span": 1})
    assert win.status_code == 200, win.text
    body = win.json()
    assert body.get("ok") is True
    assert len(body["figures"]) == 1
    src = body["figures"][0]["image_src"]
    assert src.startswith("data:image/")
    raw = base64.b64decode(src.split(",", 1)[1])
    assert len(raw) > 500


def test_window_rejects_bad_span_and_unknown_session() -> None:
    client = TestClient(app)
    bad = client.get("/api/session/ses_missing/figures/window", params={"center": 0, "span": 9})
    # Unknown session → 404 before span; or 400 for span — either fail-closed.
    assert bad.status_code in (400, 404)
    app_mod._SESSIONS["ses_test129"] = PaperSession(
        title="t",
        sentences=[Sentence(id="s1", text="hi")],
        figures=[Figure(id="fig-1", image_src="", caption="Fig. 1")],
    )
    try:
        r = client.get(
            "/api/session/ses_test129/figures/window",
            params={"center": 0, "span": 9},
        )
        assert r.status_code == 400
        assert r.json().get("error") == "bad_span"
    finally:
        app_mod._SESSIONS.pop("ses_test129", None)


def test_figure_data_url_rejects_traversal(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(pc, "cache_root", lambda: tmp_path)
    assert pc.figure_data_url("../etc", "fig-1") is None
    assert pc.figure_data_url("abcd1234ef", "../x") is None
    assert pc.figure_data_url("abcd1234ef", "fig-1") is None
