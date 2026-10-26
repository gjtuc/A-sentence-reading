"""design/466 — chemical-name titles survive, and a glued title becomes the card."""

from __future__ import annotations

from sentence_reading import title_replay as tr
from sentence_reading.llm import evidence_bus as eb
from sentence_reading.models import Sentence

NAME = "Bis(2,2,6,6-tetramethyl-3,5-heptanedionato)nickel(II)"


def test_locant_commas_are_not_an_author_list():
    assert not tr.looks_like_author_dump("Bis(2,2,6,6-tetramethyl-3,5-")
    assert tr.title_usable(NAME)
    assert tr.looks_like_author_dump("Smith, J., Kim, H., Lee, K., Park, S.")


def test_wrapped_lines_join_at_the_hyphen():
    lines = [
        (9.0, "BIS(2,2,6,6-TETRAMETHYL-3,5-HEPTANEDIONATO)NICKEL(II)"),
        (13.9, "Bis(2,2,6,6-tetramethyl-3,5-"),
        (13.9, "heptanedionato)nickel(II)"),
        (9.5, "(used as catalyst for polymerizations, oxidations)"),
    ]
    assert tr.join_largest_title_lines(lines) == NAME
    assert tr.polish_title("Bis(2,2,6,6-tetramethyl-3,5- heptanedionato)nickel(II)") == NAME
    assert tr.polish_title("Pd- and Ni-Catalyzed Coupling of Aryl Halides").startswith("Pd- and")


def test_glued_title_is_split_into_a_card():
    rows = [
        Sentence(id="sent_000000", text=NAME + " (used as catalyst for cross-coupling reactions)", section="body"),
        Sentence(id="sent_000001", text="Alternative names include Ni(TMHD)<sub>2</sub>.", section="body"),
    ]
    out, card = tr.align_title_sentences(rows, NAME)
    assert card == "split"
    assert [s.section for s in out] == ["title", "body", "body"]
    assert out[0].text == NAME
    assert out[1].text == "(used as catalyst for cross-coupling reactions)"
    assert out[1].id == "sent_000000"


def test_title_only_sentence_becomes_the_card():
    rows = [Sentence(id="sent_000000", text=NAME + ".", section="body")]
    out, card = tr.align_title_sentences(rows, NAME)
    assert card == "split"
    assert [(s.section, s.text) for s in out] == [("title", NAME)]


def test_body_not_opening_with_the_title_is_left_alone():
    rows = [Sentence(id="a", text="Nickel catalysts are widely used in coupling chemistry.", section="body")]
    out, card = tr.align_title_sentences(rows, NAME)
    assert card == "absent"
    assert out == rows


def test_existing_card_is_still_aligned_not_split():
    rows = [
        Sentence(id="t", text="heptanedionato)nickel(II)", section="title"),
        Sentence(id="b", text=NAME + " is a catalyst.", section="body"),
    ]
    out, card = tr.align_title_sentences(rows, NAME)
    assert card == "replaced"
    assert [s.section for s in out] == ["title", "body"]


def test_evidence_keeps_the_upload_file_name():
    name = "Encyclopedia_of_Reagents_-_2024_-_Sherwood_-_Bis_nickel_II.pdf"
    det = eb._safe_details({"file_name": name, "file_name_0": name, "reason": "bytes_missing"})
    assert det["file_name"] == name
    assert det["file_name_0"] == name
    assert det["reason"] == "bytes_missing"
    assert "title_text" not in eb._safe_details({"title_text": "Some Paper Title"})
