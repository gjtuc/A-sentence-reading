#!/usr/bin/env python3
"""Replay the ingest extract path on a local docx or pdf (design/294).

Prints ASCII JSON counts and title tokens only. Does not print paper text
(Windows cp949 consoles crash on names in core.xml). Does not call Gemini.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from sentence_reading.docx.extract import (  # noqa: E402
    extract_figures,
    extract_text,
    figure_source_census,
)
from sentence_reading.pdf.extract import extract_text as extract_pdf_text  # noqa: E402
from sentence_reading.pdf.sentences import (  # noqa: E402
    split_into_sentences_detailed,
    split_stub_stats,
)
from sentence_reading.pdf.supplementary_detect import (  # noqa: E402
    detect_doc_role_detailed,
)
from sentence_reading.title_replay import (  # noqa: E402
    docx_core_title,
    pdf_info_title,
    pdf_styled_title,
    title_replay_fields,
)


def _dump(payload: dict) -> None:
    print(json.dumps(payload, ensure_ascii=True))


def main() -> int:
    parser = argparse.ArgumentParser(description="Replay extract counts")
    parser.add_argument("docx", type=Path)
    parser.add_argument("--min-fig", type=int, default=None)
    parser.add_argument("--max-stub", type=int, default=None)
    args = parser.parse_args()
    path: Path = args.docx
    if not path.is_file():
        _dump({"ok": False, "error": "file_missing"})
        return 2

    kind = path.suffix.lower()
    info_title = ""
    census = {
        "blip_n": 0,
        "imagedata_n": 0,
        "caption_n": 0,
        "vml_unseen_n": 0,
    }
    figures: list = []
    figures_skipped = 0
    if kind == ".pdf":
        text = extract_pdf_text(path)
        info_title = pdf_info_title(path)
        figures_skipped = 1
    else:
        text = extract_text(path)
        info_title = docx_core_title(path)
        figures = extract_figures(path)
        census = figure_source_census(path)

    role_hit = detect_doc_role_detailed(text, filename=path.name)
    sentences, splitter = split_into_sentences_detailed(text)
    stats = split_stub_stats(sentences, splitter=splitter)
    try:
        import pysbd  # noqa: F401

        pysbd_importable = 1
    except ImportError:
        pysbd_importable = 0

    styled = ""
    if kind == ".pdf":
        try:
            styled = pdf_styled_title(path)
        except Exception:  # noqa: BLE001
            styled = ""
    payload = {
        "ok": True,
        "kind": "pdf" if kind == ".pdf" else "docx",
        "bytes": path.stat().st_size,
        "text_char_n": len(text),
        "doc_role": str(getattr(role_hit, "role", "") or ""),
        "fig_n": len(figures),
        "figures_skipped": figures_skipped,
        "pysbd_importable": pysbd_importable,
        **census,
        "splitter": splitter,
        "sentence_n": int(stats.get("sentence_n") or 0),
        "stub_caption_n": int(stats.get("stub_caption_n") or 0),
        **title_replay_fields(
            info_title=info_title,
            filename=path.name,
            text=text,
            sentences=sentences,
            title_guess="",
            styled_title=styled,
        ),
    }
    if census.get("vml_unseen_n", 0) and not figures:
        payload["verdict"] = "figures_vml_unseen"
    elif int(stats.get("stub_caption_n") or 0) > 0:
        payload["verdict"] = "caption_stub_cards"
    else:
        payload["verdict"] = "none"
    _dump(payload)
    if args.min_fig is not None and payload["fig_n"] < args.min_fig:
        return 2
    if args.max_stub is not None and payload["stub_caption_n"] > args.max_stub:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
