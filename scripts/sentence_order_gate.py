#!/usr/bin/env python3
"""
design/322 — does the stored sentence order match the paper's order?

Only one sentence is ever on screen, so a reader cannot notice a reordering.
This gate compares the stored order against the source PDF two ways:

  A. Section block order — where each section's header sits in the source text
     vs. where its sentence block sits in the stored list.
  B. Sentence anchor monotonicity — each sentence's own position in the source,
     counting how often the stored order steps backwards.

Output is ASCII JSON with counts, section keys, and integer offsets only.
Never prints paper text (design/301 — the Windows console dies on cp949).

Usage:
  python scripts/sentence_order_gate.py --cache-id <id>
  python scripts/sentence_order_gate.py --all
  python scripts/sentence_order_gate.py --pdf <path> --session <session.json>
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

CACHE_DIR = ROOT / "data" / "cache" / "papers"

# Headers whose position in the source is unambiguous enough to anchor a block.
_SECTION_HEADER_RE = {
    "abstract": r"\babstract\b",
    "introduction": r"\bintroduction\b",
    "experimental": r"\b(experimental|materials and methods)\b",
    "methods": r"\bmethods?\b",
    "results": r"\bresults\b",
    "discussion": r"\bdiscussion\b",
    "conclusion": r"\bconclusions?\b",
    "acknowledgement": r"\backnowledg",
    "references": r"\breferences\b",
    "appendix": r"\bappendix\b",
}

_ANCHOR_NGRAM = 6
_MIN_TOKENS = 5


def norm(text: str) -> str:
    """Lowercase, strip markup, collapse to single-spaced alphanumerics."""
    s = re.sub(r"<[^>]+>", " ", text or "")
    s = s.lower()
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def raw_text_from_pdf(pdf_path: Path) -> str:
    from sentence_reading.pdf import extract as pdf_extract

    pages = pdf_extract.extract_text_by_page(pdf_path)
    return pdf_extract.join_page_texts(pages)


def anchor_pos(needle_norm: str, hay_norm: str, hay_len: int) -> int:
    """First source offset for any n-gram of the sentence. -1 when unanchored."""
    toks = needle_norm.split()
    if len(toks) < _MIN_TOKENS:
        return -1
    span = min(_ANCHOR_NGRAM, len(toks))
    for start in range(0, max(1, len(toks) - span + 1)):
        gram = " ".join(toks[start : start + span])
        if len(gram) < 12:
            continue
        at = hay_norm.find(gram)
        if at >= 0:
            return at
    # Long sentences sometimes only survive as a shorter run.
    if len(toks) >= 8:
        gram = " ".join(toks[:4])
        if len(gram) >= 12:
            return hay_norm.find(gram)
    return -1


def section_blocks(sections: list[str]) -> list[tuple[str, int, int]]:
    """Contiguous runs of one section label: (key, first_index, count)."""
    out: list[tuple[str, int, int]] = []
    for i, key in enumerate(sections):
        if out and out[-1][0] == key:
            k, first, n = out[-1]
            out[-1] = (k, first, n + 1)
        else:
            out.append((key, i, 1))
    return out


def check(pdf_path: Path, session_path: Path) -> dict:
    meta = json.loads(session_path.read_text(encoding="utf-8"))
    rows = [r for r in (meta.get("sentences") or []) if isinstance(r, dict)]
    stored = [(str(r.get("text") or ""), str(r.get("section") or "")) for r in rows]

    report: dict = {
        "cache_id": session_path.parent.name,
        "sentence_n": len(stored),
        "pdf_kb": int(pdf_path.stat().st_size / 1024),
    }
    if not stored:
        report["skip"] = "no_sentences"
        return report

    raw = raw_text_from_pdf(pdf_path)
    hay = norm(raw)
    report["source_norm_chars"] = len(hay)

    # ---- A. section block order vs source header order
    labels = [sec for _, sec in stored]
    blocks = section_blocks(labels)
    report["section_block_order"] = [b[0] for b in blocks]
    report["section_block_n"] = len(blocks)
    # A repeated label in non-adjacent blocks means the block itself is split.
    seen: dict[str, int] = {}
    split_labels = []
    for key, _first, _n in blocks:
        seen[key] = seen.get(key, 0) + 1
    for key, cnt in seen.items():
        if cnt > 1:
            split_labels.append(f"{key}:{cnt}")
    report["split_section_blocks"] = sorted(split_labels)

    header_at: dict[str, int] = {}
    for key, pat in _SECTION_HEADER_RE.items():
        m = re.search(pat, hay)
        if m:
            header_at[key] = m.start()
    report["source_header_order"] = [
        k for k, _ in sorted(header_at.items(), key=lambda kv: kv[1])
    ]
    stored_order_seen: list[str] = []
    for key, _first, _n in blocks:
        if key in header_at and key not in stored_order_seen:
            stored_order_seen.append(key)
    report["stored_header_order"] = stored_order_seen
    src_rank = {k: i for i, k in enumerate(report["source_header_order"])}
    header_inversions = 0
    pairs_checked = 0
    for i in range(len(stored_order_seen)):
        for j in range(i + 1, len(stored_order_seen)):
            a, b = stored_order_seen[i], stored_order_seen[j]
            if a in src_rank and b in src_rank:
                pairs_checked += 1
                if src_rank[a] > src_rank[b]:
                    header_inversions += 1
    report["section_pairs_checked"] = pairs_checked
    report["section_order_inversions"] = header_inversions

    # ---- B. sentence anchor monotonicity
    positions: list[int] = []
    unanchored = 0
    for text, _sec in stored:
        at = anchor_pos(norm(text), hay, len(hay))
        if at < 0:
            unanchored += 1
        positions.append(at)
    anchored = [p for p in positions if p >= 0]
    report["anchored_n"] = len(anchored)
    report["unanchored_n"] = unanchored
    back = 0
    big_back = 0
    prev = -1
    for p in anchored:
        if prev >= 0 and p < prev:
            back += 1
            if (prev - p) > 2000:
                big_back += 1
        prev = max(prev, p)
    report["backward_steps"] = back
    report["backward_steps_over_2k"] = big_back
    if anchored:
        report["anchor_backward_pct"] = round(100.0 * back / len(anchored), 2)

    # Per-section median source offset — reveals a block moved wholesale.
    med: list[dict] = []
    for key, first, n in blocks:
        seg = [p for p in positions[first : first + n] if p >= 0]
        if not seg:
            continue
        seg.sort()
        med.append(
            {
                "section": key,
                "stored_at": first,
                "n": n,
                "src_median": seg[len(seg) // 2],
            }
        )
    report["blocks"] = med
    block_inv = 0
    for i in range(1, len(med)):
        if med[i]["src_median"] < med[i - 1]["src_median"]:
            block_inv += 1
    report["block_median_inversions"] = block_inv

    report["verdict"] = verdict(report)
    return report


def verdict(r: dict) -> list[str]:
    out: list[str] = []
    if r.get("section_order_inversions"):
        out.append(
            "section_order_scrambled:"
            f"{r['section_order_inversions']}/{r.get('section_pairs_checked', 0)}"
        )
    if r.get("block_median_inversions"):
        out.append(f"section_block_moved:{r['block_median_inversions']}")
    if r.get("split_section_blocks"):
        out.append("section_block_split:" + ",".join(r["split_section_blocks"]))
    pct = r.get("anchor_backward_pct")
    if isinstance(pct, (int, float)) and pct > 20.0:
        out.append(f"sentence_order_backward_pct:{pct}")
    n = r.get("sentence_n") or 0
    if n and r.get("unanchored_n", 0) > n * 0.35:
        out.append(f"low_anchor_rate:{r['unanchored_n']}/{n}")
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cache-id")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--pdf")
    ap.add_argument("--session")
    args = ap.parse_args()

    jobs: list[tuple[Path, Path]] = []
    if args.pdf and args.session:
        jobs.append((Path(args.pdf), Path(args.session)))
    elif args.cache_id:
        d = CACHE_DIR / args.cache_id
        jobs.append((d / "source.pdf", d / "session.json"))
    elif args.all:
        for d in sorted(CACHE_DIR.glob("*")):
            if (d / "source.pdf").is_file() and (d / "session.json").is_file():
                jobs.append((d / "source.pdf", d / "session.json"))
    else:
        ap.error("need --cache-id, --all, or --pdf with --session")

    if not jobs:
        print(json.dumps({"ok": False, "error": "no_paper_with_source"}))
        return 2

    reports = []
    for pdf_path, session_path in jobs:
        if not pdf_path.is_file() or not session_path.is_file():
            reports.append(
                {"cache_id": session_path.parent.name, "skip": "missing_file"}
            )
            continue
        try:
            reports.append(check(pdf_path, session_path))
        except Exception as exc:  # noqa: BLE001
            reports.append(
                {
                    "cache_id": session_path.parent.name,
                    "error": type(exc).__name__,
                }
            )

    bad = [r for r in reports if r.get("verdict")]
    print(
        json.dumps(
            {
                "ok": not bad,
                "paper_n": len(reports),
                "flagged_n": len(bad),
                "reports": reports,
            },
            ensure_ascii=True,
            indent=2,
        )
    )
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
