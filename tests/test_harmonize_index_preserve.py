"""design/169o — save_paper_session must preserve harmonize_* index fields."""

from __future__ import annotations

from sentence_reading.cache import paper_cache as pc
from sentence_reading.models import PaperSession, Sentence


def test_save_preserves_harmonize_index_fields(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(pc, "cache_root", lambda: tmp_path)
    monkeypatch.setattr(pc, "_write_index", pc._write_index)  # use real
    session = PaperSession(
        title="Harmonize Preserve Paper Title Long Enough",
        sentences=[
            Sentence(id="1", text="Hello world sentence one.", section="abstract", text_ko="안녕"),
        ],
        figures=[],
    )
    entry = pc.save_paper_session(session, source="pdf", ingest_status="ok")
    assert entry is not None
    cid = str(entry["id"])
    patched = pc.patch_index_entry(
        cid,
        harmonize_pending=True,
        harmonize_total=305,
        harmonize_done=80,
        harmonize_failed=0,
        harmonize_attempt_n=1,
    )
    assert patched is not None
    assert patched.get("harmonize_pending") is True

    session2 = PaperSession(
        title=session.title,
        sentences=list(session.sentences),
        figures=[],
        translate_digests={"abstract": {"en": "t", "ko": "요"}},
    )
    again = pc.save_paper_session(
        session2, source="pdf", ingest_status="ok", force_cache_id=cid
    )
    assert again is not None
    row = pc.get_index_entry(cid)
    assert row is not None
    assert row.get("harmonize_pending") is True
    assert int(row.get("harmonize_total") or 0) == 305
    assert int(row.get("harmonize_done") or 0) == 80
