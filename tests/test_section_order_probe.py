"""design/301 — probe must not crash on © and must read content-desc."""

from __future__ import annotations

from pathlib import Path

from sentence_reading.pdf.section_order_probe import (
    ascii_head,
    format_report,
    parse_reader_ui,
    probe_blocks,
)

ROOT = Path(__file__).resolve().parents[1]
DESIGN = ROOT / "docs/design/301-section-order-probe.md"
README = ROOT / "docs/design/README.md"
RULE = ROOT / ".cursor/rules/section-order-probe.mdc"
SCRIPT = ROOT / "scripts/section_order_probe.py"

# Elsevier page-0 shape: left is article info + Introduction, right is the abstract.
_MARKERS = (
    ("article_info", r"A R T I C L E I N F O"),
    ("abs_banner", r"A B S T R A C T"),
    ("keywords", r"Keywords:"),
    ("intro", r"1\. Introduction"),
    ("title", r"TITLE_LINE"),
    ("abs_body", r"ABSTRACT_BODY_TOKEN"),
    ("copyright", r"All rights are reserved"),
)


def _elsevier_front_blocks() -> list[tuple[float, float, float, float, str]]:
    return [
        (235.0, 33.0, 360.0, 48.0, "Renewable Energy 244"),
        (37.0, 161.0, 483.0, 185.0, "TITLE_LINE calcium doped"),
        (37.0, 206.0, 350.0, 226.0, "TongYuan Xu"),
        (37.0, 269.0, 117.0, 280.0, "A R T I C L E I N F O"),
        (202.0, 269.0, 258.0, 280.0, "A B S T R A C T"),
        (37.0, 288.0, 113.0, 310.0, "Keywords: perovskite"),
        (202.0, 288.0, 560.0, 380.0, "ABSTRACT_BODY_TOKEN cathode"),
        (37.0, 394.0, 100.0, 410.0, "1. Introduction"),
        (37.0, 415.0, 290.0, 500.0, "INTRO_PROSE modular silent cells"),
        (37.0, 714.0, 470.0, 730.0, "All rights are reserved \u00a9 2025 Elsevier"),
    ]


def test_design_301_locked() -> None:
    text = DESIGN.read_text(encoding="utf-8")
    assert "Status: **locked**" in text
    assert "301 |" in README.read_text(encoding="utf-8")
    assert "section_order_probe.py" in RULE.read_text(encoding="utf-8")
    assert "content-desc" in SCRIPT.read_text(encoding="utf-8") or "parse_reader_ui" in SCRIPT.read_text(
        encoding="utf-8"
    )


def test_ascii_head_drops_copyright_sign() -> None:
    assert "\u00a9" not in ascii_head("All rights \u00a9 reserved")
    assert "?" in ascii_head("All rights \u00a9 reserved")


def test_ui_reads_content_desc_not_text() -> None:
    xml = """<?xml version="1.0" encoding="UTF-8"?>
<hierarchy>
<node text="" content-desc="Evaluation of calcium doped Ba-Co-Nb-O perovskite as cathode materials" />
<node text="" content-desc="Abstract&#10;1 / 67" class="android.view.View">
<node text="" content-desc="All rights are reserved, including those for text and data mining, AI training." />
</node></hierarchy>"""
    ui = parse_reader_ui(xml)
    assert ui["label_n"] == 3
    assert ui["section"] == {"name": "Abstract", "position": 1, "total": 67}
    assert ui["sentence_head"].startswith("All rights are reserved")


def test_elsevier_front_page_puts_intro_before_abstract_body() -> None:
    report = probe_blocks(_elsevier_front_blocks(), page_width=595.3, markers=_MARKERS)
    assert report["multicolumn"] is True
    assert report["vision_repair_expected"] is True
    order = report["marker_order"]
    assert order.index("intro") < order.index("abs_body")
    assert report["intro_before_abstract_body"] is True
    rendered = format_report(report)
    assert rendered.isascii()
    assert "\u00a9" not in rendered
    assert "vision_repair_expected True" in rendered
