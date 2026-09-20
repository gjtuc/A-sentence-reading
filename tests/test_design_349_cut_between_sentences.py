"""design/349 — the cut that split a sentence in two.

design/347 cleared the ruler and left a small number of genuine losses. Placing each
one in its chunk gave the answer at once — they sat at the **end**:

    cata13  chunk 7   99% in
    d4cs    chunk 1   94% in
    d4cs    chunk 5   98% in
    d4cs    chunk 12  88% and 96% in
    d4cs    chunk 13  97% in
    d4cs    chunk 17  99% in
    d4cs    chunk 22  96% in
    d4cs    chunk 24  99% in
    d4cs    chunk 26  97% in

and one pair sat on **both sides of the same cut**: chunk 24 at 99% and chunk 25 at 2%.

`chunk_raw_text` had two paths. The plain-text one looked for a sentence end before
cutting; the section-pinned one cut at exactly `size`. Since the reading-order service
always marks sections, the pinned path is the one live takes. A sentence straddling the
cut reached the model as a fragment at the end of one chunk and another fragment at the
start of the next, and the prompt says to drop *incomplete fragments* — so both halves
went.

Measured over the nine papers with a stored source: **75 of 76** cuts inside a section
ended mid-sentence. Now **0 of 78**.
"""

from __future__ import annotations

from sentence_reading.llm.debone import _split_keeping_sentences, chunk_raw_text
from sentence_reading.pdf.section_flow import section_mark, strip_section_mark

SENT = "The catalyst was dried at 120 degrees for twelve hours before the run. "
CLOSERS = '.?!:)]"'


def test_a_cut_lands_after_a_sentence_end() -> None:
    body = SENT * 200
    pieces = _split_keeping_sentences(body, 1000)
    assert len(pieces) > 1
    for piece in pieces[:-1]:
        assert piece.rstrip().endswith("."), piece[-40:]


def test_no_sentence_is_split_across_two_pieces() -> None:
    """The whole point: a sentence must live in exactly one chunk."""
    body = SENT * 120
    pieces = _split_keeping_sentences(body, 900)
    rejoined = " ".join(pieces)
    assert rejoined.count("The catalyst") == body.count("The catalyst")
    for piece in pieces:
        assert piece.strip().startswith("The catalyst")


def test_the_pinned_path_cuts_the_same_way() -> None:
    """The path live takes. It used to cut at exactly `size`."""
    body = SENT * 400
    text = f"{section_mark('experimental')}\n{body}"
    chunks = chunk_raw_text(text, size=1200)
    assert len(chunks) > 1
    for c in chunks[:-1]:
        work = strip_section_mark(c).rstrip()
        assert work.endswith("."), work[-40:]


def test_every_pinned_chunk_keeps_its_section_mark() -> None:
    text = f"{section_mark('results')}\n{SENT * 300}"
    chunks = chunk_raw_text(text, size=1100)
    assert len(chunks) > 1
    for c in chunks:
        assert c.startswith(section_mark("results"))


def test_nothing_is_dropped_by_the_new_split() -> None:
    body = SENT * 150 + "A final clause without a period"
    pieces = _split_keeping_sentences(body, 800)
    assert sum(len(p) for p in pieces) >= len(body.strip()) - 2 * len(pieces)
    assert pieces[-1].endswith("without a period")


def test_a_paragraph_break_is_preferred_when_present() -> None:
    body = (SENT * 12).strip() + "\n\n" + (SENT * 12).strip()
    pieces = _split_keeping_sentences(body, len(SENT) * 13)
    assert pieces[0].endswith(".")


def test_text_with_no_break_still_gets_cut() -> None:
    """A table dump has no sentence end. It must not become one giant chunk."""
    body = "col1 col2 col3 " * 400
    pieces = _split_keeping_sentences(body, 500)
    assert len(pieces) > 1
    assert all(len(p) <= 500 for p in pieces)


def test_a_short_body_is_one_piece() -> None:
    assert _split_keeping_sentences(SENT, 5000) == [SENT.strip()]
    assert _split_keeping_sentences("", 5000) == []


def test_a_break_too_early_in_the_window_is_not_taken() -> None:
    """Cutting at the first period would make chunks tiny and multiply model calls, so
    a boundary is only taken past a third of the window."""
    body = "Short. " + "x" * 3000 + ". tail here."
    pieces = _split_keeping_sentences(body, 1000)
    assert not pieces[0].endswith("Short.")
    assert len(pieces[0]) > 500
