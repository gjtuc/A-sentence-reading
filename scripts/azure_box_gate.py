"""design/302 — Azure box gate. Booleans only. No paper text on the console."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from sentence_reading.pdf.azure_box_gate import (  # noqa: E402
    checklist,
    fixture_report,
    format_fixture_report,
    format_live_report,
    inventory_row,
    role_parse_ok,
)


def _ascii_stdout() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def _live(pdf: Path, out: Path | None) -> int:
    from sentence_reading.llm.env import (
        azure_document_intelligence_available,
        load_asr_env,
    )

    load_asr_env()
    if not azure_document_intelligence_available():
        sys.stdout.write("azure_unavailable\n")
        return 2

    import fitz

    from sentence_reading.pdf.layout_map import analyze_layout_map
    from sentence_reading.pdf.section_flow import boxes_from_azure_result, order_boxes

    doc = fitz.open(pdf)
    try:
        _layout, _client, result = analyze_layout_map(pdf)
        boxes, pages = boxes_from_azure_result(result, doc)
    finally:
        doc.close()
    raw_roles = [box.role for box in boxes if box.role]
    ordered = order_boxes(boxes, pages)
    report = checklist(ordered)
    report["role_parse_ok"] = role_parse_ok(raw_roles)
    if out is not None:
        out.parent.mkdir(parents=True, exist_ok=True)
        payload = [inventory_row(box) for box in boxes]
        out.write_text(json.dumps(payload), encoding="utf-8")
        sys.stdout.write(f"inventory_rows {len(payload)}\n")
    sys.stdout.write(format_live_report(report))
    return 0 if "live_ok True" in format_live_report(report) else 1


def main() -> int:
    _ascii_stdout()
    parser = argparse.ArgumentParser(description="Azure box gate (no paper dump)")
    parser.add_argument("--pdf", type=Path, default=None)
    parser.add_argument("--out", type=Path, default=None, help="UTF-8 inventory, no paper text")
    parser.add_argument("--fixtures-only", action="store_true")
    args = parser.parse_args()
    fixtures = fixture_report()
    sys.stdout.write(format_fixture_report(fixtures))
    if not all(fixtures.values()):
        return 1
    if args.fixtures_only or args.pdf is None:
        return 0
    if not args.pdf.is_file():
        sys.stdout.write("pdf_missing\n")
        return 1
    return _live(args.pdf, args.out)


if __name__ == "__main__":
    raise SystemExit(main())
