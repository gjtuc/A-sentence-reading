# -*- coding: utf-8 -*-
"""design/489 - paper, peer review file or general document."""

from __future__ import annotations

import json

from sentence_reading.cache import paper_cache as pc
from sentence_reading.cache.supplementary_library import (
    apply_pairing_pass,
    library_tag_for,
    list_entries_for_api,
)
from sentence_reading.models import PaperSession, Sentence
from sentence_reading.pdf.doc_kind import detect_doc_kind, normalize_doc_kind
from sentence_reading.pdf.supplementary_detect import detect_doc_role_detailed

H1 = "a" * 64
TITLE = "Nickel copper alloy methane dry reforming study title"

PAPER = (
    "Nickel copper alloy methane dry reforming\n"
    "Abstract\nWe report a catalyst.\n1. Introduction\nMethane matters.\n"
    "References\n1. Smith, J. et al. Nature 2020."
)
REVIEW = "REVIEWER COMMENTS\nReviewer #1 (Remarks to the Author):\nThe paper is fine."
REVIEW_BY_NUMBER = "Reviewer #1\nPlease add controls.\nReviewer #2\nThe method is unclear."
MANUAL = "MASsoft 7 user guide\nInstall the program.\nClick Start to begin a run."


def test_a_paper_stays_a_paper() -> None:
    assert detect_doc_kind(PAPER) == "paper"


def test_a_review_file_is_found_by_its_head_line() -> None:
    assert detect_doc_kind(REVIEW) == "review"


def test_two_numbered_reviewers_make_a_review() -> None:
    assert detect_doc_kind(REVIEW_BY_NUMBER) == "review"
    assert detect_doc_kind("Reviewer #1\nPlease add controls.\nAbstract\nx") == "paper"


def test_no_paper_sign_makes_a_general_document() -> None:
    assert detect_doc_kind(MANUAL) == "general"
    assert detect_doc_kind(MANUAL + "\nSee doi: 10.1021/acs.123") == "paper"
    assert detect_doc_kind("사용 설명서\n초록\n이 장치는") == "paper"


def test_empty_text_stays_a_paper() -> None:
    assert detect_doc_kind("") == "paper"
    assert normalize_doc_kind("odd") == "paper"


def test_a_review_file_named_like_si_is_main() -> None:
    det = detect_doc_role_detailed(REVIEW, filename="41467_2021_24079_MOESM2_ESM.pdf")
    assert det.role == "main" and det.reason == "peer_review"
    si = detect_doc_role_detailed(PAPER, filename="41467_2021_24079_MOESM1_ESM.pdf")
    assert si.role == "supplementary"


def test_library_tag_says_the_kind() -> None:
    assert library_tag_for({"doc_kind": "review"}) == "심사 기록"
    assert library_tag_for({"doc_kind": "general"}) == "일반 글"
    assert library_tag_for({"doc_kind": "paper"}) == "메인"
    assert library_tag_for({}) == "메인"
    assert library_tag_for({"doc_role": "supplementary", "doc_kind": "general"}) == "보충"


def test_a_review_does_not_pair_with_si() -> None:
    key = pc.normalize_title_key(TITLE)
    main = {"id": "aaaaaaaaaaaa", "title": TITLE, "title_key": key, "doc_kind": "review"}
    si = {"id": "bbbbbbbbbbbb", "title": TITLE, "title_key": key, "doc_role": "supplementary"}
    apply_pairing_pass([main, si])
    assert "paired_cache_id" not in main and "paired_cache_id" not in si
    main["doc_kind"] = "paper"
    apply_pairing_pass([main, si])
    assert main.get("paired_cache_id") == "bbbbbbbbbbbb"


def test_the_list_row_carries_the_kind() -> None:
    rows = list_entries_for_api(
        [{"id": "aaaaaaaaaaaa", "title": TITLE, "title_key": "k", "doc_kind": "general"}]
    )
    assert rows[0]["doc_kind"] == "general" and rows[0]["library_tag"] == "일반 글"


def test_save_keeps_the_kind_when_a_later_save_omits_it(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(pc, "cache_root", lambda: tmp_path / "papers")
    s = PaperSession(
        title=TITLE, sentences=[Sentence(id="s-1", text="One.", section="body")], figures=[]
    )
    a = pc.save_paper_session(s, debone=True, content_hash=H1, doc_kind="review")
    assert a and a["doc_kind"] == "review"
    b = pc.save_paper_session(s, debone=True, content_hash=H1)
    assert b and b["id"] == a["id"] and b["doc_kind"] == "review"
    meta = json.loads((tmp_path / "papers" / a["id"] / "session.json").read_text("utf-8"))
    assert meta["doc_kind"] == "review"
