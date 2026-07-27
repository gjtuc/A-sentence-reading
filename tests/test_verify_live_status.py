"""verify_live_status 계약 (배포 후 확인 · design/25)."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "verify_live_status.py"


def _load():
    spec = importlib.util.spec_from_file_location("verify_live_status", SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_check_status_ok() -> None:
    m = _load()
    assert m.check_status({"ok": True, "version": "0.2.33"}, expect_version="0.2.33") == []


def test_check_status_version_mismatch() -> None:
    m = _load()
    errs = m.check_status({"ok": True, "version": "0.2.31"}, expect_version="0.2.33")
    assert any("version_got" in e for e in errs)


def test_check_status_ok_false() -> None:
    m = _load()
    assert "ok_not_true" in m.check_status({"ok": False, "version": "0.2.33"}, expect_version="0.2.33")


def test_fetch_rejects_edge_urls() -> None:
    m = _load()
    with pytest.raises(ValueError, match="empty"):
        m.fetch_status("")
    with pytest.raises(ValueError, match="https"):
        m.fetch_status("http://example.com/api/status")
    with pytest.raises(ValueError, match="https"):
        m.fetch_status("ftp://nope")


def test_deploy_script_prefers_cloud_run_url_env() -> None:
    text = (ROOT / "scripts" / "deploy_cloud_run.sh").read_text(encoding="utf-8")
    assert "ASR_CLOUD_RUN_URL" in text
    assert "verify_live_status.py" in text
