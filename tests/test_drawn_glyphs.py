"""design/433 — unnamed glyphs named once per paper; the PDF's own sub/superscripts."""

from __future__ import annotations

from collections import Counter

import pymupdf
import pytest

from sentence_reading.pdf import drawn_glyphs as dg


def _g(c, x, size=8.0, oy=100.0, key=None):
    w = size * 0.5
    return dg.Glyph(c, (x, oy - size, x + w, oy + 1), size, x, oy, key=key)


def _row(spec):
    """spec: (text, size, oy) runs laid left to right."""
    out, x = [], 10.0
    for text, size, oy in spec:
        for c in text:
            out.append(_g(c, x, size, oy))
            x += size * 0.5
    return out


def test_scripts_from_size_and_baseline():
    row = _row([("0.25 mg", 8.0, 100.0), ("Pt", 5.64, 101.3), (" cm", 8.0, 100.0), ("2", 5.64, 96.44)])
    dg.mark_scripts(row)
    marks = "".join(g.script[:2] if g.script else "." for g in row)
    assert marks == "." * 7 + "susu" + "..." + "su"


def test_small_text_on_its_own_baseline_is_not_a_script():
    row = _row([("Table 1", 8.0, 100.0), (" note", 6.0, 100.0)])
    dg.mark_scripts(row)
    assert not any(g.script for g in row)


def test_script_measured_against_its_neighbour_not_the_line():
    # A row whose second half sits 3.6 pt higher: `N2` there is a subscript.
    row = _row([("CVD100/N", 8.0, 105.0), ("2", 5.6, 106.3), (" 120 N", 8.0, 101.4), ("2", 5.6, 102.7)])
    dg.mark_scripts(row)
    assert [g.script for g in row if g.c == "2" and g.size < 6] == ["sub", "sub"]


def test_unnamed_glyph_takes_its_name_and_joins_the_word():
    key = ("AdvP4C4E74", 6)
    row = [_g("c", 10), _g("m", 14), _g("\x03", 18, 5.64, 96.44, key=key), _g("2", 21, 5.64, 96.44)]
    dg.mark_scripts(row)
    assert [w[4] for w in dg.words_from_lines([row], {})] == ["cm", "2"]
    assert [w[4] for w in dg.words_from_lines([row], {key: "\u2212"})] == ["cm\u22122"]
    assert row[2].script == "sup"


def test_glyph_names_spell_characters():
    assert dg.text_from_glyph_name("minus") == "\u2212"
    assert dg.text_from_glyph_name("uni2212") == "\u2212"
    assert dg.text_from_glyph_name("fi") == "fi"
    assert dg.text_from_glyph_name("C121") == ""
    assert dg.text_from_glyph_name(".notdef") == ""
    assert dg.text_from_glyph_name("uniF8FF") == ""


def test_dash_kind_from_where_it_is_used():
    seen = dg._Seen(n=4, script=3)
    assert dg.dash_by_context("-", seen) == dg.MINUS
    seen = dg._Seen(n=4, between_digits=4)
    assert dg.dash_by_context("\u2014", seen) == dg.EN_DASH
    seen = dg._Seen(n=4, signs_a_number=3)
    assert dg.dash_by_context("\u2013", seen) == dg.MINUS
    assert dg.dash_by_context("\u03b2", dg._Seen(n=4, script=4)) == "\u03b2"


def test_vision_answer_parsing():
    raw = 'Sure: {"1": "U+00B0", "2": "\u2212", "3": " ", "4": "", "5": "toolong", "9": "x"}'
    assert dg.parse_vision_answer(raw, 5) == {1: "\u00b0", 2: "\u2212", 3: " "}
    assert dg.parse_vision_answer("no json", 3) == {}


def _scripted(text_runs):
    row = _row(text_runs)
    dg.mark_scripts(row)
    return row


def test_forms_need_agreement_and_letters(monkeypatch):
    rows = [
        _scripted([("loading mg", 8.0, 100.0), ("Pt", 5.6, 101.3), (" cm", 8.0, 100.0), ("\u22122", 5.6, 96.4)]),
        _scripted([("in cm", 8.0, 100.0), ("-2", 5.6, 96.4), (" and ", 8.0, 100.0), ("12", 5.6, 96.4)]),
        _scripted([("ratio x2 and x", 8.0, 100.0), ("2", 5.6, 96.4)]),
    ]

    class Doc:
        def __init__(self):
            self.page_count = 1
            self._asr_glyph_fixes = dg.GlyphFixes()
            self._asr_glyph_lines = {0: rows}

    forms = dg.script_forms(Doc())
    assert forms["mgPt"] == "mg<sub>Pt</sub>"
    # Two dash spellings agree on where the markup sits; the first one printed wins the tie.
    assert forms["cm-2"] == "cm<sup>\u22122</sup>"
    # A lone superscript has no letters to anchor it.
    assert "12" not in forms
    # `x2` is printed plain once and marked once: no agreement.
    assert "x2" not in forms


def test_degree_lookalike_becomes_degree():
    row = _scripted([("300 ", 8.0, 100.0), ("o", 5.6, 96.4), ("C", 8.0, 100.0)])
    word = dg._row_words(row, {})[1]
    assert dg._marked(dg._strip_word(word)) == "\u00b0C"


def test_apply_forms_to_sentence():
    forms = {"mgPt": "mg<sub>Pt</sub>", "cm-2": "cm<sup>\u22122</sup>", "H2SO4": "H<sub>2</sub>SO<sub>4</sub>"}
    text = "Loading was 0.25 mgPt cm-2, in (H2SO4) and <i>H2SO4</i> mg<sub>Pt</sub>."
    out, n = dg.apply_script_forms(text, forms)
    assert out == (
        "Loading was 0.25 mg<sub>Pt</sub> cm<sup>\u22122</sup>, in (H<sub>2</sub>SO<sub>4</sub>) "
        "and <i>H2SO4</i> mg<sub>Pt</sub>."
    )
    assert n == 3


def test_apply_forms_skips_unbalanced_tokens():
    out, n = dg.apply_script_forms("cm<sup>-2 x</sup>", {"cm-2": "cm<sup>\u22122</sup>"})
    assert n == 0 and out == "cm<sup>-2 x</sup>"


def test_one_paper_resolves_once(monkeypatch):
    calls = Counter()

    def compute():
        calls["n"] += 1
        return dg.GlyphFixes(text={("F", 1): "x"})

    dg._BY_FILE.pop("digest-433", None)
    a = dg._by_digest("digest-433", compute)
    b = dg._by_digest("digest-433", compute)
    assert a is b and calls["n"] == 1
    dg._BY_FILE.pop("digest-433", None)


def test_real_pdf_words_match_mupdf_and_scripts_found(tmp_path):
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 100), "loading 0.25 mg", fontsize=10)
    x = 72 + pymupdf.get_text_length("loading 0.25 mg", fontsize=10)
    page.insert_text((x, 101.6), "Pt", fontsize=7)
    x += pymupdf.get_text_length("Pt", fontsize=7)
    page.insert_text((x, 100), " cm", fontsize=10)
    x += pymupdf.get_text_length(" cm", fontsize=10)
    page.insert_text((x, 95.5), "2", fontsize=7)
    path = tmp_path / "s.pdf"
    doc.save(path)
    doc.close()

    doc = pymupdf.open(path)
    page = doc[0]
    want = [w[4] for w in page.get_text("words")]
    got = [w[4] for w in dg.words_from_lines(dg.page_glyph_lines(page), {})]
    assert got == want
    assert dg.doc_glyph_fixes(doc).text == {}
    forms = dg.script_forms(doc)
    assert forms.get("mgPt") == "mg<sub>Pt</sub>"
    assert forms.get("cm2") == "cm<sup>2</sup>"
    doc.close()
    assert dg.script_forms_for_path(path).get("mgPt") == "mg<sub>Pt</sub>"


@pytest.mark.parametrize("value", ["0", "off"])
def test_vision_switch(monkeypatch, value):
    monkeypatch.setenv("ASR_GLYPH_VISION", value)
    assert dg.vision_enabled() is False
