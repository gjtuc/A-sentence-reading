"""Worker registry copies stay compatible when the release version matches."""

from pathlib import Path

from scripts.check_api_worker_images_match import images_compatible


def test_same_digest_matches() -> None:
    img = "repo/asr-sentence-reading@sha256:abc"
    assert images_compatible(img, img, "0.3.306", "0.3.306", "0.3.306")


def test_worker_copy_matches_when_release_version_agrees() -> None:
    api = "repo/asr-sentence-reading@sha256:abc"
    worker = "repo/asr-sentence-reading-worker@sha256:def"
    assert images_compatible(api, worker, "0.3.306", "0.3.306", "0.3.306")


def test_worker_copy_rejects_version_mismatch() -> None:
    api = "repo/asr-sentence-reading@sha256:abc"
    worker = "repo/asr-sentence-reading-worker@sha256:def"
    assert not images_compatible(api, worker, "0.3.306", "0.3.305", "0.3.306")


def test_wrapper_success_line_is_exact() -> None:
    text = (Path(__file__).resolve().parents[1] / "scripts" / "ship_cloud_pair.ps1").read_text(
        encoding="utf-8"
    )
    assert "(?m)^design/292: ship_release OK" in text
    assert 'notmatch "ship_release OK"' not in text
    api = "repo/asr-sentence-reading@sha256:abc"
    worker = "repo/other@sha256:def"
    assert not images_compatible(api, worker, "0.3.306", "0.3.306", "0.3.306")
