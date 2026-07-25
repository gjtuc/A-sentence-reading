"""GCS sync · object path · edge cases (네트워크 없이 mock)."""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from sentence_reading.llm import gcs_sync as gcs


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("ASR_GCS_BUCKET", raising=False)
    monkeypatch.delenv("ASR_GCS_PREFIX", raising=False)
    gcs.reset_gcs_client_cache()
    yield
    gcs.reset_gcs_client_cache()


def test_disabled_without_bucket(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ASR_GCS_BUCKET", raising=False)
    cfg = gcs.gcs_config()
    assert cfg.enabled is False
    st = gcs.gcs_status()
    assert st["enabled"] is False
    assert st["ready"] is False
    assert gcs.upload_bytes("asr/tts_cache/x.mp3", b"abc") is False
    assert gcs.download_bytes("asr/tts_cache/x.mp3") is None


def test_object_name_and_tts_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ASR_GCS_BUCKET", "my-bucket")
    monkeypatch.setenv("ASR_GCS_PREFIX", "asr")
    assert gcs.object_name("tts_cache", "abc.mp3") == "asr/tts_cache/abc.mp3"
    assert gcs.tts_cache_object("deadbeefcafebabe01234567") == (
        "asr/tts_cache/deadbeefcafebabe01234567.mp3"
    )
    assert gcs.notes_object("cache:paper1") == "asr/notes/cache_paper1.json"


def test_path_traversal_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ASR_GCS_BUCKET", "b")
    assert gcs.object_name("..", "etc") is None
    assert gcs.object_name("tts_cache", "../x.mp3") is None
    assert gcs.tts_cache_object("../evil") is None
    assert gcs.tts_cache_object("") is None
    assert gcs.tts_cache_object("a/b") is None  # slash in key
    assert gcs.upload_bytes("asr/../etc/passwd", b"x") is False
    assert gcs.download_bytes("/etc/passwd") is None
    assert gcs.download_bytes("other/tts_cache/x.mp3") is None  # wrong prefix


def test_bad_prefix_falls_back(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ASR_GCS_BUCKET", "b")
    monkeypatch.setenv("ASR_GCS_PREFIX", "../hack")
    assert gcs.gcs_config().prefix == "asr"


def test_empty_upload_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ASR_GCS_BUCKET", "b")
    monkeypatch.setenv("GOOGLE_APPLICATION_CREDENTIALS", __file__)
    assert gcs.upload_bytes("asr/tts_cache/x.mp3", b"") is False
    assert gcs.upload_bytes("asr/tts_cache/x.mp3", None) is False  # type: ignore[arg-type]


def test_upload_download_with_fake_client(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("ASR_GCS_BUCKET", "test-bucket")
    monkeypatch.setenv("ASR_GCS_PREFIX", "asr")
    cred = tmp_path / "sa.json"
    cred.write_text("{}", encoding="utf-8")
    monkeypatch.setenv("GOOGLE_APPLICATION_CREDENTIALS", str(cred))

    store: dict[str, bytes] = {}

    class FakeBlob:
        def __init__(self, name: str):
            self.name = name

        def upload_from_string(self, data: bytes, content_type: str = "") -> None:
            store[self.name] = data

        def exists(self) -> bool:
            return self.name in store

        def download_as_bytes(self) -> bytes:
            return store[self.name]

    class FakeBucket:
        def blob(self, name: str) -> FakeBlob:
            return FakeBlob(name)

    class FakeClient:
        def bucket(self, name: str) -> FakeBucket:
            assert name == "test-bucket"
            return FakeBucket()

    gcs.reset_gcs_client_cache()
    with patch.object(gcs, "_storage_client", return_value=FakeClient()):
        # ready checks import + cred file
        ready, msg = gcs.gcs_client_ready()
        assert ready is True, msg
        obj = gcs.tts_cache_object("abc123def456abc123def456")
        assert obj
        assert gcs.upload_bytes(obj, b"mp3data", content_type="audio/mpeg") is True
        assert store[obj] == b"mp3data"
        assert gcs.download_bytes(obj) == b"mp3data"
        assert gcs.blob_exists(obj) is True
        assert gcs.download_bytes("asr/tts_cache/missing.mp3") is None


def test_status_ready_false_without_creds(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("ASR_GCS_BUCKET", "b")
    # WHY: load_asr_env 가 실제 SA 경로를 setdefault 할 수 있어 없는 파일로 강제
    monkeypatch.setenv(
        "GOOGLE_APPLICATION_CREDENTIALS", str(tmp_path / "missing-sa.json")
    )
    st = gcs.gcs_status()
    assert st["enabled"] is True
    assert st["ready"] is False
    assert st["tts_cache_sync"] is True


def test_synthesize_fetches_gcs_on_local_miss(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from sentence_reading.llm import tts as tts_mod

    cache_dir = tmp_path / "tts"
    cache_dir.mkdir()
    monkeypatch.setenv("ASR_TTS_CACHE_DIR", str(cache_dir))
    monkeypatch.setenv("GOOGLE_APPLICATION_CREDENTIALS", str(tmp_path / "sa.json"))
    (tmp_path / "sa.json").write_text("{}", encoding="utf-8")

    key = tts_mod.cache_key("hello world", "en-US-Neural2-D", 1.0)
    fetched = {"n": 0}

    def fake_fetch(k: str, path: Path) -> bytes | None:
        fetched["n"] += 1
        assert k == key
        path.write_bytes(b"FROM_GCS")
        return b"FROM_GCS"

    monkeypatch.setattr(tts_mod, "_try_gcs_fetch", fake_fetch)
    monkeypatch.setattr(tts_mod, "tts_available", lambda: True)
    monkeypatch.setattr(
        tts_mod,
        "_synthesize_uncached",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("should not synthesize")),
    )

    out = tts_mod.synthesize_mp3("hello world", voice="en-US-Neural2-D")
    assert out == b"FROM_GCS"
    assert fetched["n"] == 1
    assert (cache_dir / f"{key}.mp3").read_bytes() == b"FROM_GCS"


if __name__ == "__main__":
    # lightweight without pytest if needed
    import sys

    sys.exit(pytest.main([__file__, "-q"]))
