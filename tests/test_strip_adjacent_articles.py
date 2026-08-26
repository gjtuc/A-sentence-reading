"""design/136 — strip adjacent articles; keep first only (0.3.67 · rich-v15)."""

from __future__ import annotations

from pathlib import Path

import fitz
from fastapi.testclient import TestClient

from sentence_reading.api.app import app
from sentence_reading.llm.typography import PIPELINE_VERSION
from sentence_reading.pdf.adjacent_articles import (
    AdjacentArticlesError,
    find_article_start_pages,
    plan_first_article,
    prepare_pdf_first_article,
    strip_adjacent_enabled,
)

ROOT = Path(__file__).resolve().parents[1]
DESIGN = ROOT / "docs" / "design" / "136-strip-adjacent-articles.md"
PUB = ROOT / "mobile" / "pubspec.yaml"
TYPO = ROOT / "src" / "sentence_reading" / "llm" / "typography.py"
SYNTH = ROOT / "testdata" / "adjacent_papers" / "synthetic_two_articles.pdf"
OA = ROOT / "testdata" / "adjacent_papers" / "oa_merged_two_articles.pdf"


def _build_synth(path: Path) -> None:
    """Alpha pp1-3 + Beta pp4-5 (same as scripts/build_adjacent_fixtures)."""
    doc = fitz.open()
    for i in range(3):
        p = doc.new_page(width=420, height=560)
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
        p = doc.new_page(width=420, height=560)
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
    path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(path)
    doc.close()


def _single_paper(path: Path) -> None:
    doc = fitz.open()
    p = doc.new_page(width=420, height=560)
    p.insert_text((36, 70), "Only One Paper About DRM Catalysts", fontsize=13)
    p.insert_text((36, 100), "Eve Single", fontsize=11)
    p.insert_text((36, 130), "Department of Chemistry, Solo University", fontsize=10)
    p.insert_text((36, 160), "Corresponding author: eve@example.edu", fontsize=10)
    p.insert_text((36, 190), "https://doi.org/10.1000/asr.adjacent.solo", fontsize=9)
    p.insert_text((36, 230), "Abstract", fontsize=12)
    p.insert_text((36, 260), "Single paper abstract.", fontsize=10)
    p2 = doc.new_page(width=420, height=560)
    p2.insert_text((36, 70), "1. Introduction", fontsize=12)
    p2.insert_text((36, 100), "Body continues. " * 30, fontsize=10)
    doc.save(path)
    doc.close()


def test_status_and_docs_pin_strip_adjacent():
    st = TestClient(app).get("/api/status").json()
    assert st["version"] == "0.3.67"
    assert st["pipeline_version"] == "rich-v15"
    assert st["strip_adjacent"] is True
    assert st["mobile_strip_adjacent"] is True
    assert PIPELINE_VERSION == "rich-v15"
    assert "rich-v15" in TYPO.read_text(encoding="utf-8")
    assert "0.3.67" in PUB.read_text(encoding="utf-8")
    assert DESIGN.is_file()
    assert "ASR_STRIP_ADJACENT" in DESIGN.read_text(encoding="utf-8")


def test_synth_plan_keeps_alpha_only(tmp_path: Path):
    pdf = tmp_path / "synth.pdf"
    _build_synth(pdf)
    doc = fitz.open(pdf)
    texts = [p.get_text("text") or "" for p in doc]
    doc.close()
    starts = find_article_start_pages(texts)
    assert starts[0] == 0
    assert 3 in starts
    plan = plan_first_article(texts)
    assert plan.trimmed is True
    assert plan.keep_end_exclusive == 3
    out, plan2 = prepare_pdf_first_article(pdf)
    assert plan2.trimmed is True
    assert out != pdf
    trimmed = fitz.open(out)
    try:
        assert len(trimmed) == 3
        t0 = trimmed[0].get_text("text") or ""
        assert "Synthetic Paper Alpha" in t0
        assert "Synthetic Paper Beta" not in (trimmed[i].get_text("text") or "" for i in range(len(trimmed)))
    finally:
        trimmed.close()
        Path(out).unlink(missing_ok=True)


def test_single_paper_not_trimmed(tmp_path: Path):
    pdf = tmp_path / "one.pdf"
    _single_paper(pdf)
    out, plan = prepare_pdf_first_article(pdf)
    assert plan.trimmed is False
    assert out == pdf


def test_empty_pages_fail():
    try:
        plan_first_article([])
        raise AssertionError("expected AdjacentArticlesError")
    except AdjacentArticlesError as exc:
        assert "빈" in str(exc) or "empty" in str(exc).lower()


def test_kill_switch_skips(tmp_path: Path, monkeypatch):
    pdf = tmp_path / "synth.pdf"
    _build_synth(pdf)
    monkeypatch.setenv("ASR_STRIP_ADJACENT", "0")
    assert strip_adjacent_enabled() is False
    out, plan = prepare_pdf_first_article(pdf)
    assert out == pdf
    assert plan.reason == "kill_off"
    st = TestClient(app).get("/api/status").json()
    assert st["strip_adjacent"] is False


def test_oa_merged_fixture_if_present():
    """Optional local fixture from scripts/build_adjacent_fixtures.py."""
    if not OA.is_file():
        return
    out, plan = prepare_pdf_first_article(OA)
    assert plan.trimmed is True
    assert plan.keep_end_exclusive == 42  # paper A length
    doc = fitz.open(out)
    try:
        assert len(doc) == 42
        assert "Honeycomb" in (doc[0].get_text("text") or "")
    finally:
        doc.close()
        if out != OA:
            Path(out).unlink(missing_ok=True)


def test_null_and_pathish_text_do_not_crash():
    # Boundary: garbage page text must not throw; page0 still starts.
    pages = ["../etc/passwd\x00" + ("x" * 80), "1. Introduction\n" + ("body " * 40)]
    starts = find_article_start_pages(pages)
    assert starts == [0]


def test_multi_doi_without_second_start_fail_closed():
    """Two distinct front-matter DOIs on page 0 and no second start → refuse."""
    p0 = (
        "Ambiguous Bundle Title\n"
        "Department of Chemistry, Alpha University\n"
        "Corresponding author: a@example.edu\n"
        "https://doi.org/10.1000/asr.fail.a\n"
        "https://doi.org/10.1000/asr.fail.b\n"
        "Abstract\n"
        "Looks like one cover but two paper ids.\n"
    )
    p1 = "1. Introduction\n" + ("body text " * 40)
    try:
        plan_first_article([p0, p1])
        raise AssertionError("expected AdjacentArticlesError")
    except AdjacentArticlesError as exc:
        msg = str(exc)
        assert "경계" in msg or "여러 논문" in msg


def test_figure_caption_corresponding_to_not_a_start():
    """EDGE: 'corresponding to monoclinic' must not trip Correspond*."""
    from sentence_reading.pdf.adjacent_articles import _looks_like_article_start

    fig = (
        "Fig. 2. XRD diagrams obtained from powdered samples. "
        "Main diffraction peaks corresponding to monoclinic zirconia are indicated.\n"
        "The TPR results indicated that cerium reduction starts at low temperature.\n"
    )
    assert _looks_like_article_start(fig) is False
