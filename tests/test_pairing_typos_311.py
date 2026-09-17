"""Library pairing accepts five character edits on the stored title only."""

from sentence_reading.cache.paper_cache import pairing_keys_within_typos
from sentence_reading.cache.supplementary_library import apply_pairing_pass


def test_library_pairs_title_within_five_edits() -> None:
    main = {
        "id": "main1",
        "title": "Recent advances in promoting dry reforming of methane",
        "doc_role": "main",
    }
    si = {
        "id": "si1",
        "title": "Recent advancse in promoting dry reforming of methane",
        "doc_role": "supplementary",
    }
    other = {
        "id": "main2",
        "title": "Platinum encapsulated within a bacterial nanosandwich",
        "doc_role": "main",
    }
    rows = [main, si, other]
    apply_pairing_pass(rows)
    assert main["paired_cache_id"] == "si1"
    assert si["paired_cache_id"] == "main1"
    assert "paired_cache_id" not in other
    assert pairing_keys_within_typos(main["title"], si["title"])


def test_library_does_not_pair_distant_titles() -> None:
    main = {
        "id": "main1",
        "title": "Recent advances in promoting dry reforming of methane",
        "doc_role": "main",
    }
    si = {
        "id": "si1",
        "title": "Creation of Pd Al2O3 catalyst by a spray process",
        "doc_role": "supplementary",
    }
    apply_pairing_pass([main, si])
    assert not main.get("paired_cache_id")
    assert not si.get("paired_cache_id")
