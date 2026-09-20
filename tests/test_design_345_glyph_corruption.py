"""design/345 — characters the paper never printed, reaching the reader.

Tracing design/344's losses on `1-s2.0-S1385894724017960` turned up something worse
than loss. One run of that PDF produced sentences reading

    Pr?<sub>h</sub>t?<sub>h</sub>nic and electr?<sub>h</sub>nic h?<sub>h</sub>le …

every `o` replaced by a two-character sequence, **1,483 times**, and those sentences
went to the reader. The next run of the same PDF was clean. An earlier run of an RSC
review did the same with `y` → `γ` (`Catalγsis`, `Honeγwell`) 440 times.

The PDF's own embedded text was correct in every case and is deterministic, so this is
the extractor varying between calls, not the paper.

Measured over twelve runs: a corrupted extraction scores 2.87 or 27.67 marks per 1000
characters, a clean one 0.000 to 0.201.
"""

from __future__ import annotations

from sentence_reading.llm.debone_quality import (
    CORRUPTION_PER_1K_WARN,
    ChunkStat,
    build_ingest_quality,
    corruption_per_1k,
    glyph_corruption_marks,
    quality_to_warnings,
)
from sentence_reading.models import Sentence

CLEAN = (
    "Protonic and electronic hole conductivity of grain interior and grain boundaries "
    "was measured by impedance spectroscopy over a wide range of oxygen partial "
    "pressure, and the catalyst retained its activity for forty hours on stream."
)


def test_the_elsevier_shape_is_caught() -> None:
    """A one-letter subscript with the word continuing after it."""
    bad = "Pr?<sub>h</sub>t?<sub>h</sub>nic and electr?<sub>h</sub>nic h?<sub>h</sub>le"
    assert glyph_corruption_marks(bad) == 4


def test_the_rsc_shape_is_caught() -> None:
    """A Greek letter inside a Latin word."""
    assert glyph_corruption_marks("Catal\u03b3sis and Hone\u03b3well") == 2


def test_a_digit_inside_a_word_is_caught() -> None:
    assert glyph_corruption_marks("phen0men0n") >= 1


def test_clean_prose_scores_nothing() -> None:
    assert glyph_corruption_marks(CLEAN) == 0
    assert corruption_per_1k(CLEAN * 4) == 0.0


# ------------------------------------------------- what must not be mistaken for it


def test_a_real_subscript_is_not_corruption() -> None:
    """`e<sub>g</sub> filling` and `t<sub>ion</sub>` are how papers print labels."""
    for good in (
        "The e<sub>g</sub> filling of surface B sites governs activity.",
        "t<sub>ion</sub> of the bulk conduction decreases with humidity.",
        "We measured H<sub>2</sub>O and CO<sub>2</sub> uptake at 500 K.",
        "The K<sub>obs</sub> values were compared across the samples.",
    ):
        assert glyph_corruption_marks(good) == 0, good


def test_a_greek_letter_as_its_own_word_is_not_corruption() -> None:
    assert glyph_corruption_marks("the \u03b3-Al2O3 phase and \u03b4 oxygen") == 0


def test_a_chemical_token_with_digits_is_not_corruption() -> None:
    assert glyph_corruption_marks("BZY10 and SP60 and CoFe2O4 samples") == 0


def test_a_short_text_is_not_scored() -> None:
    """A ratio over a few hundred characters is not a measurement."""
    assert corruption_per_1k("Catal\u03b3sis") == 0.0


# ------------------------------------------------- the threshold and the warning


def test_the_threshold_sits_in_the_measured_gap() -> None:
    assert 0.201 < CORRUPTION_PER_1K_WARN < 2.87


def test_a_corrupted_paper_is_reported() -> None:
    bad = "Pr?<sub>h</sub>t?<sub>h</sub>nic c?<sub>h</sub>nductivity " * 40
    iq = build_ingest_quality(
        raw_text=bad,
        sentences=[Sentence(id="s1", text=bad, section="body")],
        chunk_stats=[
            ChunkStat(index=0, chars_in=900, sentences_out=1, ok=True, kind="substantive")
        ],
        ungrounded_ids=[],
    )
    assert iq.glyph_corruption_per_1k >= CORRUPTION_PER_1K_WARN
    assert "glyph_corruption_per_1k" in iq.to_dict()
    assert any(x.startswith("glyph_corruption:") for x in quality_to_warnings(iq))


def test_a_clean_paper_says_nothing() -> None:
    iq = build_ingest_quality(
        raw_text=CLEAN * 4,
        sentences=[Sentence(id="s1", text=CLEAN * 4, section="body")],
        chunk_stats=[
            ChunkStat(index=0, chars_in=900, sentences_out=1, ok=True, kind="substantive")
        ],
        ungrounded_ids=[],
    )
    assert iq.glyph_corruption_per_1k == 0.0
    assert not [x for x in quality_to_warnings(iq) if x.startswith("glyph_corruption")]
