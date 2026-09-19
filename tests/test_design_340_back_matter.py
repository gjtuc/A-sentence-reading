"""design/340 — the journal's apparatus is not the paper.

`strip_back_matter` (design/333) already removed licence blocks, DOI lines and
mastheads from the **coverage denominator**, so the metric called them "not practice
text" while the product handed them to the reader to say aloud. design/339 then
found the same sentences again from the other side: 10 of the 83 remaining speech
defects were back matter, and teaching TTS to read a Creative Commons URL nicely is
the wrong repair.

The judgement is on the sentence's own evidence, never on a section label: a label
can be badly wrong (design/335) and this decision removes content. Measured over the
2,366-sentence corpus, 16 sentences match and every one is apparatus.
"""

from __future__ import annotations

from sentence_reading.llm.debone_quality import (
    ChunkStat,
    build_ingest_quality,
    drop_back_matter_sentences,
    is_back_matter_sentence,
    quality_to_warnings,
)
from sentence_reading.models import Sentence

# Verbatim shapes the corpus produced as practice sentences.
APPARATUS = [
    "Author Contributions Additional Information This study was supported by the "
    "National Research Foundation.",
    "Supplementary information accompanies this paper at http://www.nature.com/srep",
    "How to cite this article: Gao, Y. et al. Creation of Pd catalysts.",
    "Rep. 7, 41797; doi: 10.1038/srep41797 (2017).",
    "Publisher's note: Springer Nature remains neutral with regard to jurisdictional "
    "claims.",
    "This work is licensed under a Creative Commons Attribution 4.0 International "
    "License.",
    "To view a copy of this license, visit http://creativecommons.org/licenses/by/4.0/",
    "Supporting Online Material www.sciencemag.org/cgi/content/full/science.1212858/DC1",
    "DOI: 10.1126/science.1212858 View the article online https://www.science.org/doi/",
    "Supplementary data to this article can be found online at https://doi.org/10.1016/j",
    "Open Access Article.",
    "Competing financial interests: The authors declare no competing interests.",
    "Data availability: the datasets are available from the corresponding author.",
]

BODY = [
    "The conversion rose steadily once the reactor reached steady state.",
    "Carbon balances closed within three percent for all of the experiments.",
    "We thank the beamline staff for their help with the measurements.",
    "The catalyst was dried at 120 degrees for 12 hours before use.",
    "Figure 3 shows the conversion as a function of temperature.",
    "This result is consistent with the mechanism proposed by Jiang and co-workers.",
    "The BET surface area of the support was 259 square meters per gram.",
]


def test_every_measured_apparatus_shape_is_caught() -> None:
    for text in APPARATUS:
        assert is_back_matter_sentence(text) is True, text


def test_body_prose_is_never_caught() -> None:
    for text in BODY:
        assert is_back_matter_sentence(text) is False, text


def test_an_acknowledgement_sentence_stays() -> None:
    """Thanking people is prose. Only the apparatus heading is apparatus.

    Dropping the whole acknowledgement *section* would mean trusting a label, which
    is the mistake design/335 was about.
    """
    assert is_back_matter_sentence("We thank A. Becker for helpful discussion.") is False


def test_a_citation_in_running_text_is_not_apparatus() -> None:
    assert (
        is_back_matter_sentence(
            "As reported previously, the selectivity follows the same trend."
        )
        is False
    )


def test_empty_and_markup_only_are_not_apparatus() -> None:
    assert is_back_matter_sentence("") is False
    assert is_back_matter_sentence("   ") is False
    assert is_back_matter_sentence("<i></i>") is False


def test_markup_does_not_hide_a_url() -> None:
    assert is_back_matter_sentence("Visit <i>http://creativecommons.org/</i> to view.") is True


def test_the_drop_returns_a_count() -> None:
    sents = [Sentence(id=f"s{i}", text=t, section="body") for i, t in enumerate(BODY)]
    sents += [
        Sentence(id=f"a{i}", text=t, section="acknowledgement")
        for i, t in enumerate(APPARATUS)
    ]
    kept, dropped = drop_back_matter_sentences(sents)
    assert dropped == len(APPARATUS)
    assert len(kept) == len(BODY)
    assert all(s.section == "body" for s in kept)


def test_nothing_to_drop_is_reported_as_nothing() -> None:
    sents = [Sentence(id=f"s{i}", text=t, section="body") for i, t in enumerate(BODY)]
    kept, dropped = drop_back_matter_sentences(sents)
    assert dropped == 0
    assert kept == sents


def test_the_drop_is_reported() -> None:
    iq = build_ingest_quality(
        raw_text=BODY[0],
        sentences=[],
        chunk_stats=[ChunkStat(index=0, chars_in=900, sentences_out=5, ok=True, kind="substantive")],
        ungrounded_ids=[],
        back_matter_dropped=16,
    )
    assert iq.back_matter_dropped == 16
    assert iq.to_dict()["back_matter_dropped"] == 16
    assert "back_matter_dropped:16" in quality_to_warnings(iq)


def test_the_denominator_and_the_stream_now_agree() -> None:
    """The point of the chip: one definition of practice text, used both ways."""
    from sentence_reading.llm.debone_quality import strip_back_matter

    for text in APPARATUS:
        removed_from_denominator = strip_back_matter(text).strip() != text.strip()
        assert removed_from_denominator or is_back_matter_sentence(text)
