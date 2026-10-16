"""design/403 - the phone app also builds for the web; Android behaviour unchanged."""

from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MOBILE = ROOT / "mobile"


def _read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def test_web_platform_folder_is_committed():
    assert (MOBILE / "web" / "index.html").exists()
    assert (MOBILE / "web" / "manifest.json").exists()
    ignored = [r.strip() for r in _read("mobile/.gitignore").splitlines()]
    assert "web/" not in ignored


def test_logout_wipe_skips_app_documents_only_on_web():
    src = _read("mobile/lib/state/library_controller.dart")
    body = src[src.index("Future<void> clearAll()") :]
    body = body[: body.index("pdfFolderGrant = null;")]
    assert "if (!kIsWeb) await _editStash.purgeAll();" in body
    assert "if (!kIsWeb) await _pdfHashCache.clearBound();" in body
    assert "await _drafts.clear();" in body
    assert "await _reserve.clear();" in body


def test_magic_link_channel_is_android_only():
    src = _read("mobile/lib/api/auth_deeplink.dart")
    assert "if (_listening || kIsWeb) return;" in src


def test_flutter_any_wrapper_never_assigns_env_drive():
    ps1 = _read("scripts/flutter_any.ps1")
    assert "SetEnvironmentVariable($pf86" in ps1
    assert "$env:ProgramFiles(x86)" not in ps1
    assert "$env:'ProgramFiles(x86)'" not in ps1
    assert "flutter_any.ps1" in _read("scripts/flutter_any.cmd")


def test_click_web_build_counts_only_real_errors():
    spec = importlib.util.spec_from_file_location("asr_click_run", ROOT / "click" / "_run.py")
    run = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(run)
    console = "\n".join(
        [
            "LOG auth deeplink pending: x",
            "UNCAUGHT Error",
            "  dart: MissingPluginException(No implementation found)",
            "LOG-ERROR Access to fetch at 'https://x/api/status' has been blocked by CORS policy: no",
            "LOG-ERROR Failed to load resource: net::ERR_FAILED https://x/api/status",
            "ERROR something else",
        ]
    )
    assert run.probe_summary(console) == {"uncaught": 1, "cors": 1, "other": 1, "drawn": 0}
    assert "web_build" in run.JOBS
    assert (ROOT / "click" / "03_web_build.bat").read_bytes().decode("ascii").count("web_build") >= 1
