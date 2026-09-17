"""테스트 공통: 실기기 env(gc_automation.env)가 계약을 깨지 않게 격리.

design/78 — production defaults ASR_EMAIL_PASSWORD off; enable it here so
fixtures that still register via email+password keep working. Tests that
assert the kill override with ASR_EMAIL_PASSWORD=0.

design/83 — production defaults ASR_LOGIN_REQUIRED on; disable here so
legacy unauth fixture routes keep working. Dedicated tests turn it back on.
"""

from __future__ import annotations

import site
import sys
import sysconfig
from pathlib import Path

import pytest


def _interpreter_package_dirs() -> set[Path]:
    """site-packages of the running interpreter.

    WHY: `pip install .` puts `sentence_reading` here, so the stale-checkout
    sweep below would drop the whole directory and take fastapi/pymupdf with
    it — CI then fails to collect every API test.
    """
    candidates: list[str] = []
    for getter in (site.getsitepackages, site.getusersitepackages):
        try:
            got = getter()
        except (AttributeError, OSError):
            continue
        if isinstance(got, str):
            candidates.append(got)
        else:
            candidates.extend(got)
    paths = sysconfig.get_paths()
    for key in ("purelib", "platlib"):
        value = paths.get(key)
        if value:
            candidates.append(value)
    resolved: set[Path] = set()
    for entry in candidates:
        try:
            resolved.add(Path(entry).resolve())
        except OSError:
            continue
    return resolved


# design/303 — a stale checkout must not satisfy `import sentence_reading`.
_SRC = Path(__file__).resolve().parents[1] / "src"
_src_s = str(_SRC)
_SITE = _interpreter_package_dirs()
_kept: list[str] = []
for _entry in sys.path:
    try:
        _resolved = Path(_entry).resolve()
    except OSError:
        _kept.append(_entry)
        continue
    if _resolved == _SRC:
        continue
    if _resolved not in _SITE and (
        _resolved / "sentence_reading" / "__init__.py"
    ).is_file():
        continue
    _kept.append(_entry)
sys.path[:] = [_src_s, *_kept]


@pytest.fixture(autouse=True)
def _isolate_asr_env(monkeypatch: pytest.MonkeyPatch) -> None:
    # WHY: 운영 PC 의 gc_automation.env(버킷·OAuth)가 setdefault 로 테스트에 섞임
    monkeypatch.setenv("ASR_SKIP_ENV_FILE", "1")
    monkeypatch.setenv("ASR_SKIP_GCS_SECRETS", "1")
    monkeypatch.setenv("ASR_EMAIL_AUTH", "0")
    monkeypatch.setenv("ASR_EMAIL_PASSWORD", "1")
    # design/83 — suite default off; test_login_required.py re-enables.
    monkeypatch.setenv("ASR_LOGIN_REQUIRED", "0")
    monkeypatch.delenv("ASR_GOOGLE_CLIENT_ID", raising=False)
    monkeypatch.delenv("ASR_KAKAO_REST_API_KEY", raising=False)
    monkeypatch.delenv("ASR_GCS_BUCKET", raising=False)
    monkeypatch.setenv("ASR_AZURE_LAYOUT", "0")
    # design/169o — suite keeps legacy inline harmonize; residual tests flip to 1.
    monkeypatch.setenv("ASR_HARMONIZE_RESIDUAL", "0")
    monkeypatch.delenv("AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT", raising=False)
    monkeypatch.delenv("AZURE_DOCUMENT_INTELLIGENCE_KEY", raising=False)
