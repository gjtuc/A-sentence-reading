"""design/124 — missing figures: honest empty slots + fig ref wiring (0.3.41)."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from sentence_reading.api.app import app
from sentence_reading.cache import paper_cache as pc
from sentence_reading.models import Figure, PaperSession, Sentence

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / "src" / "sentence_reading" / "cache" / "paper_cache.py"
APP_JS = ROOT / "src" / "sentence_reading" / "static" / "app.js"
READER = ROOT / "mobile" / "lib" / "screens" / "reader_screen.dart"
FIG_DART = ROOT / "mobile" / "lib" / "api" / "fig_refs.dart"
LIB = ROOT / "mobile" / "lib" / "state" / "library_controller.dart"
PUB = ROOT / "mobile" / "pubspec.yaml"
DESIGN = ROOT / "docs" / "design" / "124-missing-figures.md"


def test_status_version() -> None:
    st = TestClient(app).get("/api/status").json()
    assert st["version"] == "0.3.41"
    assert st["fig_ref_hints"] is True


def test_design_and_wiring() -> None:
    assert DESIGN.is_file()
    assert "0.3.38" in DESIGN.read_text(encoding="utf-8")
    assert "0.3.41" in PUB.read_text(encoding="utf-8")
    cache = CACHE.read_text(encoding="utf-8")
    assert "design/124" in cache
    assert "image_src" in cache
    assert "goToFigureIndex" in LIB.read_text(encoding="utf-8")
    reader = READER.read_text(encoding="utf-8")
    assert "hintsForSentence" in reader or "fig_refs" in reader
    assert "이미지 없음" in reader
    assert "_figRefHints" in reader
    assert "fig_ref_hints" in reader or "figRefHints" in reader
    assert FIG_DART.is_file()
    app_js = APP_JS.read_text(encoding="utf-8")
    assert "이미지 없음" in app_js
    assert "error" in app_js


def test_load_keeps_figure_when_png_missing(
    monkeypatch, tmp_path: Path
) -> None:
    import base64

    monkeypatch.setattr(pc, "cache_root", lambda: tmp_path)
    # 1×1 PNG — must decode on save or figure is dropped at write time.
    png = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
    )
    data = "data:image/png;base64," + base64.b64encode(png).decode("ascii")
    cid = "abcd1234dead"
    root = tmp_path / cid
    session = PaperSession(
        title="Missing PNG Slot Title Long Enough",
        figures=[
            Figure(id="fig-0001", image_src=data, caption="Fig. 1. Present"),
            Figure(id="fig-0002", image_src=data, caption="Fig. 2. Will lose file"),
        ],
        sentences=[Sentence(id="s1", text="See Fig. 2.", section="body")],
    )
    entry = pc.save_paper_session(session, debone=True, source="pdf")
    assert entry is not None
    # Force known cache id directory if save assigned another id.
    saved_id = str(entry.get("id") or "")
    root = tmp_path / saved_id
    lost = root / "figures" / "fig-0002.png"
    assert lost.is_file()
    lost.unlink()
    loaded, _info = pc.load_cached_session(saved_id)
    assert loaded is not None
    assert len(loaded.figures) == 2
    assert loaded.figures[0].image_src.startswith("data:image/png")
    assert loaded.figures[1].caption.startswith("Fig. 2")
    assert loaded.figures[1].image_src == ""