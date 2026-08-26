#!/usr/bin/env python3
"""Build adjacent-papers fixtures under testdata/adjacent_papers/.

A) Concatenate two downloaded arXiv PDFs (must exist locally).
B) Write synthetic_two_articles.pdf + boundary_report.json.

PDFs are gitignored; re-download with curl if missing (see README).
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import fitz

ROOT = Path(__file__).resolve().parents[1] / "testdata" / "adjacent_papers"
A = ROOT / "paper_a_arxiv2401.14543.pdf"
B = ROOT / "paper_b_arxiv2401.14123.pdf"
MERGED = ROOT / "oa_merged_two_articles.pdf"
SYNTH = ROOT / "synthetic_two_articles.pdf"
REPORT = ROOT / "boundary_report.json"


def page_head(page, n: int = 400) -> str:
    t = (page.get_text("text") or "").replace("\x00", "")
    return re.sub(r"\s+", " ", t).strip()[:n]


def build_oa_merge() -> dict:
    if not A.is_file() or not B.is_file():
        raise SystemExit(
            f"Missing {A.name} or {B.name}. See testdata/adjacent_papers/README.md"
        )
    doc_a = fitz.open(A)
    doc_b = fitz.open(B)
    n_a, n_b = len(doc_a), len(doc_b)
    merged = fitz.open()
    merged.insert_pdf(doc_a)
    merged.insert_pdf(doc_b)
    merged.save(MERGED)
    boundary = n_a
    jumps = []
    for i in range(len(merged)):
        cur = page_head(merged[i], 200)
        score = 0
        if i == boundary:
            score += 5
        if "ultrathin washcoat" in cur.lower() and i == boundary:
            score += 3
        if score >= 5:
            jumps.append(
                {
                    "page_index": i,
                    "page_1based": i + 1,
                    "score": score,
                    "head": cur[:180],
                }
            )
    out = {
        "kind": "oa_merged_arxiv",
        "sources": [
            {
                "file": A.name,
                "arxiv": "2401.14543",
                "pages": n_a,
                "url": "https://arxiv.org/abs/2401.14543",
                "page_range_0based": [0, n_a - 1],
                "page_range_1based": [1, n_a],
            },
            {
                "file": B.name,
                "arxiv": "2401.14123",
                "pages": n_b,
                "url": "https://arxiv.org/abs/2401.14123",
                "page_range_0based": [n_a, n_a + n_b - 1],
                "page_range_1based": [n_a + 1, n_a + n_b],
            },
        ],
        "merged_file": MERGED.name,
        "merged_pages": len(merged),
        "article2_start_page_index": boundary,
        "article2_start_page_1based": boundary + 1,
        "jump_hits": jumps,
        "caveat": (
            "Paper A references cite the Ultrathin title mid-document; "
            "do not treat citation mentions as article boundaries."
        ),
    }
    doc_a.close()
    doc_b.close()
    merged.close()
    return out


def build_synthetic() -> dict:
    synth = fitz.open()
    for i in range(3):
        p = synth.new_page(width=420, height=560)
        if i == 0:
            p.insert_text((36, 70), "Synthetic Paper Alpha: Nickel Catalysts for DRM", fontsize=13)
            p.insert_text((36, 100), "Ada Alpha, Ben Beta", fontsize=11)
            p.insert_text((36, 130), "Department of Chemistry, Alpha University", fontsize=10)
            p.insert_text((36, 160), "Corresponding author: ada@example.edu", fontsize=10)
            p.insert_text((36, 190), "https://doi.org/10.1000/asr.adjacent.alpha", fontsize=9)
            p.insert_text((36, 230), "Abstract", fontsize=12)
            p.insert_text((36, 260), "Alpha abstract about nickel dry reforming catalysts.", fontsize=10)
        elif i == 1:
            p.insert_text((36, 70), "1. Introduction", fontsize=12)
            p.insert_text((36, 100), "Alpha body page two. " * 20, fontsize=10)
        else:
            p.insert_text((36, 70), "2. Results", fontsize=12)
            p.insert_text((36, 100), "Alpha results continue. " * 20, fontsize=10)
            p.insert_text((36, 400), "References", fontsize=12)
            p.insert_text((36, 430), "[1] Alpha prior work.", fontsize=10)
    for i in range(2):
        p = synth.new_page(width=420, height=560)
        if i == 0:
            p.insert_text((36, 70), "Synthetic Paper Beta: Cobalt Catalysts for SRM", fontsize=13)
            p.insert_text((36, 100), "Cara Gamma, Dan Delta", fontsize=11)
            p.insert_text((36, 130), "Institute of Energy, Beta College", fontsize=10)
            p.insert_text((36, 160), "Corresponding author: cara@example.edu", fontsize=10)
            p.insert_text((36, 190), "https://doi.org/10.1000/asr.adjacent.beta", fontsize=9)
            p.insert_text((36, 230), "Abstract", fontsize=12)
            p.insert_text(
                (36, 260),
                "Beta abstract about cobalt steam reforming — different paper.",
                fontsize=10,
            )
        else:
            p.insert_text((36, 70), "1. Introduction", fontsize=12)
            p.insert_text(
                (36, 100),
                "Beta body only. Should be stripped when selecting Alpha. " * 12,
                fontsize=10,
            )
    synth.save(SYNTH)
    n = len(synth)
    synth.close()
    return {
        "kind": "synthetic_fixture",
        "file": SYNTH.name,
        "pages": n,
        "articles": [
            {
                "id": "alpha",
                "title": "Synthetic Paper Alpha: Nickel Catalysts for DRM",
                "page_range_0based": [0, 2],
                "page_range_1based": [1, 3],
            },
            {
                "id": "beta",
                "title": "Synthetic Paper Beta: Cobalt Catalysts for SRM",
                "page_range_0based": [3, 4],
                "page_range_1based": [4, 5],
            },
        ],
        "target_for_chip": "keep alpha only -> pages 0..2; strip beta from index 3",
    }


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ROOT.mkdir(parents=True, exist_ok=True)
    oa = build_oa_merge()
    syn = build_synthetic()
    REPORT.write_text(
        json.dumps({"oa_merge": oa, "synthetic": syn}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print("merged", MERGED, "pages", oa["merged_pages"])
    print("boundary 1-based page", oa["article2_start_page_1based"])
    print("synthetic", SYNTH, "pages", syn["pages"])
    print("report", REPORT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
