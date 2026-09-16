"""design/294 D5 — title replay prints tokens, never paper text."""

from __future__ import annotations

import json
from pathlib import Path

from sentence_reading.title_replay import title_class, title_replay_fields

ROOT = Path(__file__).resolve().parents[1]
REPLAY = ROOT / "scripts/replay_docx_extract.py"


def test_replay_dumps_ascii_json_only() -> None:
    text = REPLAY.read_text(encoding="utf-8")
    assert "ensure_ascii=True" in text
    assert "ensure_ascii=False" not in text
    assert "title_replay_fields" in text
    assert "sentences=sentences" in text


def test_elsevier_stem_constant_stays_in_source() -> None:
    """A sibling-regex edit must not delete the name title_class calls."""
    src = (ROOT / "src/sentence_reading/title_replay.py").read_text(encoding="utf-8")
    assert "_ELSEVIER_STEM = re.compile" in src
    assert "_ELSEVIER_STEM.match" in src


def test_si_banner_and_elsevier_stem_are_tokens() -> None:
    assert title_class("Supporting Information") == "si_banner"
    assert title_class("1-s2.0-S0960148125003246-main") == "code_like"
    assert title_class("1-s2.0-S0960148125003246-mmc1") == "code_like"
    assert title_class("") == "empty"
    fields = title_replay_fields(
        info_title="Supporting Information",
        filename="1-s2.0-S0960148125003246-mmc1.docx",
        text="Supporting Information\n\nEvaluation of calcium doped perovskite cells",
        sentences=[],
    )
    raw = json.dumps(fields, ensure_ascii=True)
    assert "Supporting Information" not in raw
    assert "Evaluation of calcium" not in raw
    assert fields["info_title_class"] == "si_banner"
    assert fields["stem_class"] == "code_like"
    assert fields["session_title_source"] == "filename_stem"
    assert fields["head_title_after_banner"] == 1
    assert fields["title_verdict"] == "info_title_si_banner"
    assert raw.isascii()
