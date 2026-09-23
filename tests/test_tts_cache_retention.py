"""Shared spoken MP3s expire after 7 days."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sentence_reading.llm.tts import expired_tts_cache_names, purge_expired_tts_cache


def test_expired_tts_names_drop_only_old_mp3() -> None:
    now = datetime(2026, 9, 23, tzinfo=timezone.utc)
    old = now - timedelta(days=8)
    fresh = now - timedelta(days=2)
    names = expired_tts_cache_names(
        [
            ("asr/tts_cache/old.mp3", old),
            ("asr/tts_cache/fresh.mp3", fresh),
            ("asr/tts_cache/note.txt", old),
            ("asr/tts_cache/unknown.mp3", None),
        ],
        now=now,
        keep_days=7,
    )
    assert names == ["asr/tts_cache/old.mp3"]


def test_local_tts_cache_deletes_week_old_files(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("ASR_TTS_CACHE_RETENTION_DAYS", raising=False)
    monkeypatch.setattr(
        "sentence_reading.llm.tts.tts_cache_dir", lambda: tmp_path
    )
    monkeypatch.setattr(
        "sentence_reading.llm.gcs_sync.gcs_client_ready",
        lambda: (False, "off"),
    )
    old = tmp_path / "old.mp3"
    fresh = tmp_path / "fresh.mp3"
    old.write_bytes(b"old")
    fresh.write_bytes(b"new")
    old_stamp = (datetime.now(timezone.utc) - timedelta(days=8)).timestamp()
    fresh_stamp = (datetime.now(timezone.utc) - timedelta(days=1)).timestamp()
    import os

    os.utime(old, (old_stamp, old_stamp))
    os.utime(fresh, (fresh_stamp, fresh_stamp))
    out = purge_expired_tts_cache()
    assert out["keep_days"] == 7
    assert out["local_deleted"] == 1
    assert not old.exists()
    assert fresh.exists()
