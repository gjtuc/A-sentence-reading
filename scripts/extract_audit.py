#!/usr/bin/env python3
"""
design/323 — one command per paper: extraction fidelity + figure completeness.

Runs the checks that need no live ingest, so many papers can be audited cheaply:

  order      design/322 — stored/split sentence order vs the source
  census     design/321 — Azure bodies vs carousel slots, statuses
  clip       design/323 — is each rendered crop cut off (ink edge touch)
  coverage   design/321 — recall against the pre-filter text

Azure is used when configured. Gemini debone runs only with --with-gemini;
without it the non-LLM splitter stands in, which still exercises ordering.

ASCII JSON only. Never prints paper text (design/301 — cp949 console).

Usage:
  python scripts/extract_audit.py --pdf a.pdf --pdf b.pdf
  python scripts/extract_audit.py --dir papers/ --out data/audit.json
  python scripts/extract_audit.py --pdf a.pdf --session <session.json>
  python scripts/extract_audit.py --pdf a.pdf --with-gemini
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def _ascii_stdout() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        pass


def _sentences_for(pdf: Path, *, with_gemini: bool, session: Path | None):
    """Return (sentences, pre_filter_text, source_note)."""
    from sentence_reading.models import Sentence
    from sentence_reading.pdf import extract as pdf_extract

    pages = pdf_extract.extract_text_by_page(pdf)
    pre = pdf_extract.join_page_texts(pages)

    if session is not None and session.is_file():
        meta = json.loads(session.read_text(encoding="utf-8"))
        rows = [r for r in (meta.get("sentences") or []) if isinstance(r, dict)]
        sents = [
            Sentence(
                id=str(r.get("id") or ""),
                text=str(r.get("text") or ""),
                section=str(r.get("section") or ""),
            )
            for r in rows
        ]
        return sents, pre, "stored_session"

    from sentence_reading.llm.vision_ocr import recover_pdf_text

    recovered = recover_pdf_text(pdf, pages)
    text = recovered.text

    if with_gemini:
        from sentence_reading.llm.debone import debone_sentences

        res = debone_sentences(text)
        if res.ok and res.sentences:
            return list(res.sentences), pre, "debone"

    from sentence_reading.pdf.sentences import split_into_sentences_detailed

    sents, via = split_into_sentences_detailed(text)
    return list(sents), pre, f"split:{via}"


def _figure_part(pdf: Path) -> dict:
    from sentence_reading.llm.env import (
        azure_document_intelligence_available,
        load_asr_env,
    )

    load_asr_env()
    if not azure_document_intelligence_available():
        return {"skip": "azure_unavailable"}

    import fitz

    from sentence_reading.pdf.caption_pairing import (
        pair_slot_captions,
        refill_empty_slots,
    )
    from sentence_reading.pdf.clip_probe import clip_report, clip_verdicts
    from sentence_reading.pdf.extract_figures_v2 import _render_slot_png
    from sentence_reading.pdf.layout_map import analyze_layout_map
    from sentence_reading.pdf.slot_plan import (
        append_unclaimed_body_slots,
        build_slot_plan,
        initial_body_assignments,
        refresh_slot_statuses,
        slot_census,
    )

    layout, client, _result = analyze_layout_map(pdf)
    doc = fitz.open(pdf)
    try:
        plan = build_slot_plan(layout)
        before_slot_n = len(plan.slots)
        initial_body_assignments(layout, plan)
        pair_slot_captions(layout, plan)
        refill_empty_slots(layout, plan)
        added = append_unclaimed_body_slots(layout, plan)
        refresh_slot_statuses(plan)
        census = slot_census(layout, plan)

        clips: list[tuple[str, object]] = []
        rows: list[dict] = []
        for slot in plan.slots:
            try:
                png, _caption, page_index = _render_slot_png(
                    doc, client, layout, slot
                )
            except Exception as exc:  # noqa: BLE001
                rows.append(
                    {
                        "slot": slot.key,
                        "status": slot.status,
                        "error": type(exc).__name__,
                    }
                )
                continue
            rep = clip_report(png)
            clips.append((slot.key, rep))
            row = {
                "slot": slot.key,
                "status": slot.status,
                "page": page_index,
                "png_bytes": len(png or b""),
            }
            if rep is not None:
                row.update(rep.to_dict())
            rows.append(row)
    finally:
        doc.close()

    out = {
        "slot_n_before_append": before_slot_n,
        "appended_slots": added,
        "census": census,
        "slots": rows,
        "verdicts": clip_verdicts(clips),
    }
    if census.get("unused_body_n"):
        out["verdicts"].append(f"figure_body_unslotted:{census['unused_body_n']}")
    if added:
        out["verdicts"].append(f"caption_number_collapse_repaired:{added}")
    return out


def audit(pdf: Path, *, with_gemini: bool, session: Path | None) -> dict:
    from sentence_reading.llm.debone_quality import (
        compute_coverage_ratio,
        order_warnings,
        source_coverage_warnings,
        source_order_stats,
    )

    rep: dict = {"pdf": pdf.name, "pdf_kb": int(pdf.stat().st_size / 1024)}

    try:
        sents, pre, note = _sentences_for(
            pdf, with_gemini=with_gemini, session=session
        )
    except Exception as exc:  # noqa: BLE001
        rep["sentence_error"] = type(exc).__name__
        sents, pre, note = [], "", "error"

    rep["sentence_source"] = note
    rep["sentence_n"] = len(sents)
    verdicts: list[str] = []

    if sents and pre:
        cov = compute_coverage_ratio(pre, sents)
        rep["source_coverage"] = round(cov, 4)
        # No debone ratio on the split path, so only the absolute recall speaks.
        verdicts.extend(
            source_coverage_warnings(source_coverage=cov, debone_coverage=0.0)
        )
        stats = source_order_stats(pre, sents)
        rep["order"] = stats
        verdicts.extend(order_warnings(stats))

    try:
        rep["figures"] = _figure_part(pdf)
        verdicts.extend(rep["figures"].get("verdicts") or [])
    except Exception as exc:  # noqa: BLE001
        rep["figures"] = {"error": type(exc).__name__}

    rep["verdicts"] = sorted(set(verdicts))
    return rep


def main() -> int:
    _ascii_stdout()
    ap = argparse.ArgumentParser()
    ap.add_argument("--pdf", action="append", default=[])
    ap.add_argument("--dir")
    ap.add_argument("--session")
    ap.add_argument("--with-gemini", action="store_true")
    ap.add_argument("--out")
    args = ap.parse_args()

    paths: list[Path] = [Path(p) for p in args.pdf]
    if args.dir:
        paths.extend(sorted(Path(args.dir).glob("*.pdf")))
    paths = [p for p in paths if p.is_file()]
    if not paths:
        print(json.dumps({"ok": False, "error": "no_pdf"}))
        return 2

    session = Path(args.session) if args.session else None
    if session is not None and len(paths) > 1:
        print(json.dumps({"ok": False, "error": "session_needs_one_pdf"}))
        return 2

    reports = [
        audit(p, with_gemini=args.with_gemini, session=session) for p in paths
    ]
    flagged = [r for r in reports if r.get("verdicts")]
    payload = {
        "ok": not flagged,
        "paper_n": len(reports),
        "flagged_n": len(flagged),
        "reports": reports,
    }
    text = json.dumps(payload, ensure_ascii=True, indent=2)
    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8")
        print(
            json.dumps(
                {
                    "ok": payload["ok"],
                    "paper_n": payload["paper_n"],
                    "flagged_n": payload["flagged_n"],
                    "out": str(out),
                },
                ensure_ascii=True,
            )
        )
    else:
        print(text)
    return 1 if flagged else 0


if __name__ == "__main__":
    raise SystemExit(main())
