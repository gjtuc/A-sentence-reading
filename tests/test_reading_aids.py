"""읽기 보조 — 음절 · (0.2.30 · design/30)."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from sentence_reading.api.app import app
from sentence_reading.reading_aids import (
    apply_reading_aids,
    syllabify_html,
    syllabify_plain,
)


def test_status() -> None:
    st = TestClient(app).get("/api/status").json()
    assert st["version"] == "0.2.30"
    assert st.get("reading_aids_syllables") is True


def test_syllabify_plain() -> None:
    out = syllabify_plain("examination")
    assert "·" in out
    assert out.replace("·", "") == "examination"
    assert syllabify_plain("Ni") == "Ni"
    assert syllabify_plain("the") == "the"


def test_syllabify_html_preserves_tags() -> None:
    raw = "H<sub>2</sub>O examination"
    out = syllabify_html(raw)
    assert "<sub>2</sub>" in out
    assert "·" in out


def test_api_aids() -> None:
    client = TestClient(app)
    res = client.post(
        "/api/reading/aids",
        json={"text": "diffraction pattern", "syllables": True},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["ok"] is True
    assert "·" in body["text"]
    off = client.post(
        "/api/reading/aids",
        json={"text": "diffraction", "syllables": False},
    ).json()
    assert off["text"] == "diffraction"
    assert apply_reading_aids("x", syllables=False) == "x"


def test_design_and_ui() -> None:
    root = Path(__file__).resolve().parents[1]
    design = (root / "docs" / "design" / "30-reading-aids.md").read_text(
        encoding="utf-8"
    )
    assert "0.2.30" in design
    html = (root / "src" / "sentence_reading" / "static" / "index.html").read_text(
        encoding="utf-8"
    )
    assert "syllableBtn" in html
    assert "pyphen" in (root / "pyproject.toml").read_text(encoding="utf-8")
