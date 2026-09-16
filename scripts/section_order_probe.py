"""design/301 — ASCII section-order probe. Do not print raw PDF text."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from sentence_reading.pdf.section_order_probe import (  # noqa: E402
    DEFAULT_MARKERS,
    format_report,
    parse_reader_ui,
    probe_pdf,
)


def _ascii_stdout() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def main() -> int:
    _ascii_stdout()
    parser = argparse.ArgumentParser(description="Section marker order (no paper dump)")
    parser.add_argument("--pdf", required=True, type=Path)
    parser.add_argument("--ui", type=Path, default=None, help="uiautomator dump XML")
    parser.add_argument(
        "--marker",
        action="append",
        default=[],
        metavar="NAME=REGEX",
        help="extra marker, repeatable; does not print the match text",
    )
    args = parser.parse_args()
    if not args.pdf.is_file():
        sys.stdout.write("pdf_missing\n")
        return 1
    extra: list[tuple[str, str]] = []
    for raw in args.marker:
        if "=" not in raw:
            sys.stdout.write("marker_bad\n")
            return 1
        name, pat = raw.split("=", 1)
        extra.append((name.strip(), pat))
    report = probe_pdf(args.pdf, markers=[*extra, *DEFAULT_MARKERS])
    ui = None
    if args.ui is not None:
        if not args.ui.is_file():
            sys.stdout.write("ui_missing\n")
            return 1
        ui = parse_reader_ui(args.ui.read_text(encoding="utf-8"))
    sys.stdout.write(format_report(report, ui))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
