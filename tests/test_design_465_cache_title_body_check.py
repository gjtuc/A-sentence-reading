"""design/465 — a title found in another file's head is not the same paper."""

from __future__ import annotations

from sentence_reading.cache.paper_cache import opening_sentences_present

OPENING = [
    "Bis(2,2,6,6-tetramethyl-3,5-heptanedionato)nickel(II) is used as a catalyst for polymerizations.",
    "Alternative names for the compound include nickel(II) bis(2,2,6,6-tetramethyl-3,5-heptanedionate).",
    "The complex sublimes under vacuum and is widely used as a precursor for nickel oxide films.",
]


def test_same_paper_reupload_matches_despite_line_breaks():
    raw = (
        "Bis(2,2,6,6-tetramethyl-3,5-\nheptanedionato)nickel(II) is used as a cata-\nlyst for polymerizations. "
        "Alternative names for the compound include nickel(II) bis(2,2,6,6-tetramethyl-3,5-heptane-\ndionate). "
        "The complex sublimes under vacuum and is widely used as a precursor for nickel oxide films."
    )
    assert opening_sentences_present(OPENING, raw)


def test_other_paper_that_names_the_compound_is_refused():
    other = (
        "Nickel oxide thin films for supercapacitor electrodes. Abstract. We deposited NiO by ALD "
        "using bis(2,2,6,6-tetramethyl-3,5-heptanedionato)nickel(II) and ozone at 250 C. "
        "The films showed a capacitance of 1200 F/g after 5000 cycles."
    )
    assert not opening_sentences_present(OPENING, other)


def test_empty_inputs_are_refused():
    assert not opening_sentences_present([], "anything at all")
    assert not opening_sentences_present(OPENING, "")
    assert not opening_sentences_present(["short"], "short")


def _try(monkeypatch, *, entry_hash: str, upload_hash: str, text: str):
    from sentence_reading.api import app as app_mod
    from sentence_reading.llm.typography import PIPELINE_VERSION
    from sentence_reading.models import PaperSession, Sentence

    session = PaperSession(
        title="heptanedionato)nickel(II)",
        sentences=[Sentence(id=str(i), text=t, section="body") for i, t in enumerate(OPENING)],
        figures=[],
    )
    hit = {
        "id": "c865b31c7d63",
        "pipeline_version": PIPELINE_VERSION,
        "analyzed_build": app_mod.app.version,
        "content_hash": entry_hash,
        "title_key": "heptanedionato nickel ii",
    }
    monkeypatch.setattr(app_mod, "find_cached_by_text", lambda *_a, **_k: dict(hit))
    monkeypatch.setattr(app_mod, "load_cached_session", lambda _cid: (session, {}))
    return app_mod._try_cache_hit(text, "pdf", content_hash=upload_hash)


def test_other_file_naming_the_title_does_not_reuse_the_archive(monkeypatch):
    other = "We used bis(2,2,6,6-tetramethyl-3,5-heptanedionato)nickel(II) as the ALD precursor."
    assert _try(monkeypatch, entry_hash="a" * 64, upload_hash="b" * 64, text=other) is None


def test_same_file_reuses_the_archive(monkeypatch):
    assert _try(monkeypatch, entry_hash="a" * 64, upload_hash="a" * 64, text="x") is not None


def test_other_file_with_the_same_body_reuses_the_archive(monkeypatch):
    body = " ".join(OPENING)
    assert _try(monkeypatch, entry_hash="a" * 64, upload_hash="b" * 64, text=body) is not None
