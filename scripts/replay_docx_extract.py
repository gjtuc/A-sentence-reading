#!/usr/bin/env python3
"""Replay the ingest extract path on a local docx (design/294).

Prints counts only: role, figure census, splitter, stub-caption cards.
Does not call Gemini. Does not change extract behavior.
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
from sentence_reading.pdf.sentences import (  # noqa: E402
    split_into_sentences_detailed,
    split_stub_stats,
)
from sentence_reading.pdf.supplementary_detect import (  # noqa: E402
    detect_doc_role_detailed,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Replay docx extract counts")
    parser.add_argument("docx", type=Path)
    parser.add_argument("--min-fig", type=int, default=None)
    parser.add_argument("--max-stub", type=int, default=None)
    args = parser.parse_args()
    path = args.docx
    if not path.is_file():
        print(json.dumps({"ok": False, "error": "file_missing"}))
        return 2

    text = extract_text(path)
    role_hit = detect_doc_role_detailed(text, filename=path.name)
    figures = extract_figures(path)
    census = figure_source_census(path)
    sentences, splitter = split_into_sentences_detailed(text)
    stats = split_stub_stats(sentences, splitter=splitter)
    try:
        import pysbd  # noqa: F401

        pysbd_importable = 1
    except ImportError:
        pysbd_importable = 0

    role_name = str(getattr(role_hit, "role", "") or "")

    payload = {
        "ok": True,
        "bytes": path.stat().st_size,
        "text_char_n": len(text),
        "doc_role": role_name,
        "fig_n": len(figures),
        "pysbd_importable": pysbd_importable,
        **census,
        "splitter": splitter,
        "sentence_n": int(stats.get("sentence_n") or 0),
        "stub_caption_n": int(stats.get("stub_caption_n") or 0),
    }
    if census.get("vml_unseen_n", 0) and not figures:
        payload["verdict"] = "figures_vml_unseen"
    elif int(stats.get("stub_caption_n") or 0) > 0:
        payload["verdict"] = "caption_stub_cards"
    else:
        payload["verdict"] = "none"
    print(json.dumps(payload, ensure_ascii=False))
    if args.min_fig is not None and payload["fig_n"] < args.min_fig:
        return 2
    if args.max_stub is not None and payload["stub_caption_n"] > args.max_stub:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
