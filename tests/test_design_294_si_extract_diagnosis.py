"""design/294 — SI extract diagnosis counts (no product extract change)."""

from __future__ import annotations

from pathlib import Path

from sentence_reading.llm.evidence_verdict import compute_pair_index_verdicts
from sentence_reading.models import Sentence
from sentence_reading.pdf.sentences import split_stub_stats

ROOT = Path(__file__).resolve().parents[1]
DESIGN = ROOT / "docs/design/294-si-extract-diagnosis.md"
KINDS_PY = ROOT / "src/sentence_reading/llm/evidence_kinds.py"
KINDS_DART = ROOT / "mobile/lib/services/evidence_kinds.dart"
FLOOR = ROOT / "src/sentence_reading/llm/evidence_floor.py"
APP = ROOT / "src/sentence_reading/api/app.py"
EXTRACT = ROOT / "src/sentence_reading/docx/extract.py"
SENT = ROOT / "src/sentence_reading/pdf/sentences.py"
REPLAY = ROOT / "scripts/replay_docx_extract.py"
README = ROOT / "docs/design/README.md"


def test_design_294_locked() -> None:
    text = DESIGN.read_text(encoding="utf-8")
    assert "Status: **locked**" in text
    assert "0.3.289" in text
    assert "sentence_split_done" in text
    assert "figures_vml_unseen" in text
    assert "Non-goals" in text
    assert "294 |" in README.read_text(encoding="utf-8")


def test_kinds_and_floor() -> None:
    py = KINDS_PY.read_text(encoding="utf-8")
    dart = KINDS_DART.read_text(encoding="utf-8")
    floor = FLOOR.read_text(encoding="utf-8")
    assert '"sentence_split_done"' in py
    assert "'sentence_split_done'" in dart
    assert '"sentence_split_done"' in floor
    app = APP.read_text(encoding="utf-8")
    assert "vml_unseen_n" in app
    assert "stub_caption_n" in app
    assert "figure_source_census" in EXTRACT.read_text(encoding="utf-8")
    assert "split_into_sentences_detailed" in SENT.read_text(encoding="utf-8")
    assert "extract_figures" in REPLAY.read_text(encoding="utf-8")


def test_vml_and_stub_verdicts() -> None:
    events = [
        {
            "kind": "figure_extract_done",
            "ok": True,
            "details": {
                "supplementary": 1,
                "empty": 1,
                "fig_n": 0,
                "vml_unseen_n": 8,
                "blip_n": 0,
            },
        },
        {
            "kind": "sentence_split_done",
            "ok": True,
            "details": {
                "splitter": "heuristic",
                "sentence_n": 11,
                "stub_caption_n": 1,
            },
        },
    ]
    verdicts = compute_pair_index_verdicts(events)
    assert "si_figure_zero_after_extract" in verdicts
    assert "figures_vml_unseen" in verdicts
    assert "caption_stub_cards" in verdicts


def test_stub_caption_stat() -> None:
    rows = [
        Sentence(id="a", text="Fig. S4."),
        Sentence(id="b", text="Tafel plots of the catalyst."),
    ]
    stats = split_stub_stats(rows, splitter="heuristic")
    assert stats["stub_caption_n"] == 1
    assert stats["sentence_n"] == 2
