"""design/481 — display equations kept as page pictures under the sentence they follow."""

from __future__ import annotations

import base64
from pathlib import Path
from types import SimpleNamespace

import pytest

from sentence_reading.cache import paper_cache as pc
from sentence_reading.llm.ingest_resume_payload import sentence_from_dict, sentence_to_dict
from sentence_reading.models import PaperSession, Sentence
from sentence_reading.pdf.equations import (
    MAX_PAPER_BYTES,
    EquationBox,
    attach_equations,
    clean_equations,
    collect_equations,
    letters,
    place_equations,
    render_equations,
)

_PNG = "data:image/png;base64,iVBORw0KGgo="


def _box(text, *, prose=False, page=0, y0=100.0, y1=120.0, x0=72.0, x1=300.0, role="", kind="paragraph"):
    return SimpleNamespace(
        text=text, prose=prose, page=page, x0=x0, y0=y0, x1=x1, y1=y1, role=role, kind=kind
    )


def _collect(rows):
    return collect_equations(
        rows, is_math=lambda t: "=" in t or "\u2013" in t or t.startswith("("), keep=lambda b: b.prose
    )


def test_equation_between_prose_keeps_both_neighbours() -> None:
    eqs = _collect(
        [
            ("body", _box("The rate follows the Arrhenius law given by", prose=True, y0=60, y1=90)),
            ("body", _box("k = A exp(-Ea/RT)", y0=100, y1=120)),
            ("body", _box("where A is the pre-exponential factor.", prose=True, y0=130, y1=150)),
        ]
    )
    assert len(eqs) == 1
    eq = eqs[0]
    assert eq.para == 1
    assert (eq.page, eq.y0, eq.y1) == (0, 100, 120)
    assert eq.before.endswith("arrheniuslawgivenby")
    assert eq.after.startswith("whereaisthe")


def test_broken_equation_and_its_number_are_one_picture() -> None:
    eqs = _collect(
        [
            ("body", _box("Prose before the equation here.", prose=True, y0=40, y1=60)),
            ("body", _box("(3)", x0=500, x1=520, y0=100, y1=112)),
            ("body", _box("y = a + b", y0=98, y1=114)),
            ("body", _box("+ c = d", y0=118, y1=132)),
            ("body", _box("Prose after.", prose=True, y0=150, y1=170)),
        ]
    )
    assert len(eqs) == 1
    assert (eqs[0].x0, eqs[0].x1, eqs[0].y0, eqs[0].y1) == (72, 520, 98, 132)


def test_lone_number_far_away_is_not_an_equation() -> None:
    eqs = _collect([("body", _box("(3)", y0=100, y1=112))])
    assert eqs == []


def test_headings_and_reference_math_are_not_equations() -> None:
    eqs = _collect(
        [
            ("body", _box("2.1.2. Synthesis of Al\u2013Ce\u2013O supports")),
            ("body", _box("x = 1", role="pageHeader")),
            ("references", _box("a = b", y0=300, y1=320)),
        ]
    )
    assert eqs == []


def test_placement_uses_text_before_then_after() -> None:
    sentences = [
        "Rates were measured at several temperatures.",
        "The rate follows the Arrhenius law given by",
        "where A is the pre-exponential factor.",
        "Second law: the energy balance reads as follows below",
        "Here the terms are listed.",
    ]
    first = EquationBox(0, 0, 0, 10, 10, before=letters(sentences[1])[-40:], para=2)
    second = EquationBox(0, 0, 20, 10, 30, before="", after=letters(sentences[4])[:40], para=4)
    lost = EquationBox(0, 0, 40, 10, 50, before="nothingofthiskindanywhereinpaper", para=5)
    assert place_equations(sentences, [first, second, lost]) == [1, 3, -1]


def test_placement_moves_forward_in_reading_order() -> None:
    sentences = ["Where x is given by", "Middle prose sentence here.", "Where x is given by"]
    probe = letters(sentences[0])
    boxes = [
        EquationBox(0, 0, 0, 1, 1, before=probe, para=1),
        EquationBox(0, 0, 2, 1, 3, before=probe, para=1),
        EquationBox(0, 0, 4, 1, 5, before=probe, para=3),
    ]
    assert place_equations(sentences, boxes) == [0, 0, 2]


def _pdf(tmp_path: Path) -> Path:
    fitz = pytest.importorskip("fitz")
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    page.insert_text((72, 110), "E = m c^2   (1)", fontsize=14)
    path = tmp_path / "eq.pdf"
    doc.save(str(path))
    doc.close()
    return path


def test_render_cuts_a_gray_png_of_the_box(tmp_path: Path) -> None:
    path = _pdf(tmp_path)
    eq = EquationBox(0, 70, 95, 240, 115)
    by_sentence, census = render_equations(path, [eq, eq, eq], [0, -1, 5], ["s0", "s1"])
    assert census["placed"] == 1 and census["unplaced"] == 2
    (row,) = by_sentence["s0"]
    assert row["src"].startswith("data:image/png;base64,")
    png = base64.b64decode(row["src"].split(",", 1)[1])
    assert png[:8] == b"\x89PNG\r\n\x1a\n"
    assert row["w"] == pytest.approx(176, abs=1) and row["h"] == pytest.approx(26, abs=1)


def test_render_skips_a_box_off_the_page(tmp_path: Path) -> None:
    path = _pdf(tmp_path)
    _, census = render_equations(
        path, [EquationBox(3, 0, 0, 50, 50), EquationBox(0, 900, 900, 950, 950)], [0, 0], ["s0"]
    )
    assert census["bad_box"] == 2 and census["placed"] == 0


def test_render_stops_at_the_paper_budget(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import sentence_reading.pdf.equations as eqmod

    path = _pdf(tmp_path)
    monkeypatch.setattr(eqmod, "MAX_PAPER_BYTES", 1)
    _, census = render_equations(path, [EquationBox(0, 70, 95, 240, 115)], [0], ["s0"])
    assert census["over_budget"] == 1 and census["placed"] == 0
    assert MAX_PAPER_BYTES >= 1_000_000


def test_attach_puts_pictures_on_the_preceding_sentence(tmp_path: Path) -> None:
    path = _pdf(tmp_path)
    sentences = [
        Sentence(id="s0", text="The energy is given by"),
        Sentence(id="s1", text="where m is the mass."),
    ]
    eq = EquationBox(0, 70, 95, 240, 115, before=letters(sentences[0].text))
    out, census = attach_equations(path, sentences, [eq])
    assert census["placed"] == 1
    assert len(out[0].equations) == 1 and out[1].equations == ()
    assert out[0].text == sentences[0].text


def test_clean_drops_bad_rows() -> None:
    rows = clean_equations(
        [
            {"id": "eq_001", "src": _PNG, "w": 120.04, "h": 20},
            {"id": "eq_002", "src": "https://x/y.png", "w": 10, "h": 10},
            {"id": "eq_003", "src": _PNG, "w": 0, "h": 10},
            {"id": "eq_004", "src": _PNG, "w": "wide", "h": 10},
            "nope",
        ]
    )
    assert rows == ({"id": "eq_001", "src": _PNG, "w": 120.0, "h": 20.0},)
    assert clean_equations(None) == ()
    assert len(clean_equations([{"src": _PNG, "w": 1, "h": 1}] * 50)) == 20


def test_equations_ride_with_the_public_session_and_resume_payload() -> None:
    eq = {"id": "eq_001", "src": _PNG, "w": 100.0, "h": 20.0}
    s = Sentence(id="s0", text="Given by", equations=(eq,))
    plain = Sentence(id="s1", text="No math.")
    data = PaperSession(title="T", sentences=[s, plain]).to_public_dict(include_images=False)
    assert data["sentences"][0]["equations"] == [eq]
    assert "equations" not in data["sentences"][1]
    back = sentence_from_dict(sentence_to_dict(s))
    assert back is not None and back.equations == (eq,)
    assert "equations" not in sentence_to_dict(plain)


def test_equations_survive_the_paper_cache(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(pc, "cache_root", lambda: tmp_path)
    eq = {"id": "eq_001", "src": _PNG, "w": 100.0, "h": 20.0}
    session = PaperSession(
        title="Equation Cache Paper Title Long Enough Here",
        sentences=[
            Sentence(id="s0", text="The energy is given by", section="body", equations=(eq,)),
            Sentence(id="s1", text="where m is the mass.", section="body"),
        ],
    )
    entry = pc.save_paper_session(session, debone=True, source="pdf")
    loaded, _ = pc.load_cached_session(entry["id"])
    assert loaded.sentences[0].equations == (eq,)
    assert loaded.sentences[1].equations == ()
