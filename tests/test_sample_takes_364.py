"""design/364 — sample take keeping must never break the recognize path."""

from __future__ import annotations

from sentence_reading.llm import sample_takes_gcs as st


def test_only_the_ten_sample_rounds_are_accepted():
    assert st.sample_round_ok(1)
    assert st.sample_round_ok(10)
    assert not st.sample_round_ok(0)
    assert not st.sample_round_ok(11)
    assert not st.sample_round_ok(-3)


def test_a_line_id_that_could_escape_the_path_is_refused():
    assert st.safe_line_id("sent_f01") == "sent_f01"
    assert st.safe_line_id("  SENT_F01 ") == "sent_f01"
    assert st.safe_line_id("../../etc/passwd") is None
    assert st.safe_line_id("") is None
    assert st.safe_line_id(None) is None
    assert st.safe_line_id("1f01") is None
    assert st.safe_line_id("a" * 33) is None


def test_two_takes_of_one_line_get_different_names():
    first = st.sample_take_stem(round_n=3, line_id="sent_f01", audio=b"aaa")
    second = st.sample_take_stem(round_n=3, line_id="sent_f01", audio=b"bbb")
    assert first and second
    assert first != second
    assert first.startswith("sent_f01_")
    assert st.sample_take_stem(round_n=99, line_id="sent_f01", audio=b"a") is None
    assert st.sample_take_stem(round_n=3, line_id="!!", audio=b"a") is None


def test_the_phone_mime_lands_on_a_playable_extension():
    assert st.take_extension("audio/mp4") == "m4a"
    assert st.take_extension("audio/mp4; codecs=mp4a") == "m4a"
    assert st.take_extension("AUDIO/WAV") == "wav"
    assert st.take_extension("") == "bin"
    assert st.take_extension(None) == "bin"


def test_a_bad_round_is_skipped_without_touching_storage(monkeypatch):
    def boom(*_a, **_k):
        raise AssertionError("must not upload")

    monkeypatch.setattr(st, "upload_bytes", boom)
    out = st.save_sample_take(
        round_n=0, line_id="sent_f01", audio=b"x", mime="audio/mp4", meta={}
    )
    assert out["take_saved"] == 0
    assert out["take_code"] == "bad_round"


def test_no_storage_is_reported_not_raised(monkeypatch):
    monkeypatch.setattr(st, "gcs_client_ready", lambda: (False, "off"))
    out = st.save_sample_take(
        round_n=2, line_id="sent_f01", audio=b"x" * 100, mime="audio/mp4", meta={}
    )
    assert out["take_saved"] == 0
    assert out["take_code"] == "gcs_unready"
    assert out["take_bytes"] == 100


def test_an_oversized_take_is_refused_before_upload(monkeypatch):
    def boom(*_a, **_k):
        raise AssertionError("must not upload")

    monkeypatch.setattr(st, "upload_bytes", boom)
    out = st.save_sample_take(
        round_n=2,
        line_id="sent_f01",
        audio=b"x" * (st.SAMPLE_TAKE_MAX_BYTES + 1),
        mime="audio/mp4",
        meta={},
    )
    assert out["take_saved"] == 0
    assert out["take_code"] == "too_large"


def test_audio_and_sidecar_both_land_under_the_round(monkeypatch):
    seen: list[tuple[str, str]] = []

    monkeypatch.setattr(st, "gcs_client_ready", lambda: (True, "ok"))
    monkeypatch.setattr(
        st,
        "personal_object_name",
        lambda *parts: "asr/users/u1/" + "/".join(parts),
    )

    def fake_upload(name, data, *, content_type="application/octet-stream"):
        seen.append((name, content_type))
        return True

    monkeypatch.setattr(st, "upload_bytes", fake_upload)
    out = st.save_sample_take(
        round_n=7,
        line_id="sent_n21",
        audio=b"audio-bytes",
        mime="audio/mp4",
        meta={"expected": "The Ni-Fe-Al catalyst", "skill_tier": 6},
    )
    assert out["take_saved"] == 1
    assert out["take_code"] == "ok"
    assert len(seen) == 2
    audio_name, audio_type = seen[0]
    meta_name, meta_type = seen[1]
    assert "/sample_takes/r07/" in audio_name
    assert audio_name.endswith(".m4a")
    assert audio_type == "audio/mp4"
    # Same stem for both, so a take and its labels cannot drift apart.
    assert meta_name == audio_name[: -len("m4a")] + "json"
    assert meta_type == "application/json"


def test_a_lost_sidecar_is_not_reported_as_saved(monkeypatch):
    monkeypatch.setattr(st, "gcs_client_ready", lambda: (True, "ok"))
    monkeypatch.setattr(
        st,
        "personal_object_name",
        lambda *parts: "asr/users/u1/" + "/".join(parts),
    )
    calls = {"n": 0}

    def flaky_upload(name, data, *, content_type="application/octet-stream"):
        calls["n"] += 1
        return calls["n"] == 1

    monkeypatch.setattr(st, "upload_bytes", flaky_upload)
    out = st.save_sample_take(
        round_n=1, line_id="sent_f01", audio=b"a", mime="audio/mp4", meta={}
    )
    assert out["take_saved"] == 0
    assert out["take_code"] == "meta_upload_failed"


def test_a_missing_uid_stops_the_write(monkeypatch):
    monkeypatch.setattr(st, "gcs_client_ready", lambda: (True, "ok"))
    monkeypatch.setattr(st, "personal_object_name", lambda *_parts: None)

    def boom(*_a, **_k):
        raise AssertionError("must not upload")

    monkeypatch.setattr(st, "upload_bytes", boom)
    out = st.save_sample_take(
        round_n=1, line_id="sent_f01", audio=b"a", mime="audio/mp4", meta={}
    )
    assert out["take_saved"] == 0
    assert out["take_code"] == "no_uid"
