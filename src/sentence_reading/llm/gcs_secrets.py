"""
Private ASR runtime secrets.

Lives in its own bucket, not `asr-chaheon-warehouse`. The paper warehouse is
listed and deleted by product code under the `asr/` prefix, and its service
account can read that bucket. This object is the copy that does not depend
on a Desktop env path. Cloud Run already receives the same keys at deploy;
this fetch is skipped there (`K_SERVICE`).

Values are never logged. The TTS private-key JSON is not stored here: the
bootstrap is the signed-in user (ADC). A key file next to these secrets would
let any reader become the warehouse service account.
"""

from __future__ import annotations

import os
from pathlib import Path

BUCKET = "asr-runtime-secrets-984608876300"
ENV_OBJECT = "secrets/asr-runtime.env"
PAPER_BUCKET = "asr-chaheon-warehouse"

# Same credential set Cloud Run injects, plus the warehouse location.
# Feature flags with code defaults stay out.
ALLOWLIST = (
    "GEMINI_API_KEY",
    "ASR_GEMINI_MODEL",
    "AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT",
    "AZURE_DOCUMENT_INTELLIGENCE_KEY",
    "ASR_AZURE_LAYOUT",
    "ASR_GOOGLE_CLIENT_ID",
    "ASR_GCS_BUCKET",
    "ASR_GCS_PREFIX",
    "ASR_ADMIN_EMAILS",
    "ASR_CLOUD_RUN_URL",
    "ASR_AUTH_SECRET",
    "ASR_KAKAO_REST_API_KEY",
    "ASR_KAKAO_CLIENT_SECRET",
    "ASR_WORKER_SECRET",
    "ASR_WORKER_URL",
    "ASR_SMTP_HOST",
    "ASR_SMTP_FROM",
    "ASR_SMTP_USER",
    "ASR_SMTP_PASS",
    "ASR_SMTP_PORT",
    "ASR_SMTP_SSL",
    "ASR_UNPAYWALL_EMAIL",
    "ASR_CROSSREF_MAILTO",
    "ASR_SHADOWING_PRACTICE",
)

_REQUIRED = (
    "GEMINI_API_KEY",
    "AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT",
    "AZURE_DOCUMENT_INTELLIGENCE_KEY",
    "ASR_AUTH_SECRET",
    "ASR_GOOGLE_CLIENT_ID",
)

_DENY_EXACT = {
    "GOOGLE_APPLICATION_CREDENTIALS",
    "MAIL_TO",
    "NAVER_EMAIL",
    "NAVER_APP_PASSWORD",
    "IPTIME_WIFI_PSK",
}
_DENY_PREFIXES = (
    "NAVER_",
    "IPTIME_",
    "DATA_PC_",
    "STOCK_",
    "SCREENER_",
    "ST_",
    "MAIL_",
)

_loaded = False


def denied(key: str) -> bool:
    if key in _DENY_EXACT:
        return True
    return key.startswith(_DENY_PREFIXES)


def select_runtime(parsed: dict[str, str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for key in ALLOWLIST:
        if denied(key):
            continue
        val = (parsed.get(key) or "").strip()
        if val:
            out[key] = val
    return out


def render_env(values: dict[str, str]) -> bytes:
    selected = select_runtime(values)
    lines = [f"{key}={selected[key]}" for key in ALLOWLIST if key in selected]
    return ("\n".join(lines) + "\n").encode("utf-8")


def parse_env_bytes(raw: bytes) -> dict[str, str]:
    out: dict[str, str] = {}
    for line in raw.decode("utf-8", errors="replace").splitlines():
        s = line.strip()
        if not s or s.startswith("#") or "=" not in s:
            continue
        key, _, val = s.partition("=")
        key = key.strip()
        if key not in ALLOWLIST or denied(key):
            continue
        val = val.strip()
        if val:
            out[key] = val
    return out


def public_members(policy: dict) -> list[str]:
    found: list[str] = []
    for binding in policy.get("bindings") or []:
        for member in binding.get("members") or []:
            if member in ("allUsers", "allAuthenticatedUsers"):
                found.append(member)
    return found


def user_adc_path() -> Path | None:
    candidates: list[Path] = []
    appdata = (os.environ.get("APPDATA") or "").strip()
    if appdata:
        candidates.append(Path(appdata) / "gcloud" / "application_default_credentials.json")
    candidates.append(Path.home() / ".config" / "gcloud" / "application_default_credentials.json")
    for path in candidates:
        if path.is_file():
            return path
    return None


def drop_missing_credentials_path() -> None:
    """A Desktop JSON path that is not on this machine must not block ADC."""
    raw = (os.environ.get("GOOGLE_APPLICATION_CREDENTIALS") or "").strip()
    if raw and not Path(raw).is_file():
        os.environ.pop("GOOGLE_APPLICATION_CREDENTIALS", None)


def _client():
    drop_missing_credentials_path()
    from google.cloud import storage

    return storage.Client()


def upload_runtime(values: dict[str, str]) -> dict[str, int]:
    """Upload the allowlisted env. Raises if a required key is empty."""
    if BUCKET == PAPER_BUCKET or ENV_OBJECT.startswith("asr/"):
        raise RuntimeError("secrets_must_not_use_paper_warehouse")
    selected = select_runtime(values)
    missing = [k for k in _REQUIRED if k not in selected]
    if missing:
        raise RuntimeError("runtime_env_missing:" + ",".join(missing))
    blob_bytes = render_env(selected)
    if any(denied(k) and k.encode() in blob_bytes for k in _DENY_EXACT):
        raise RuntimeError("runtime_env_denied_key")
    client = _client()
    bucket = client.bucket(BUCKET)
    blob = bucket.blob(ENV_OBJECT)
    blob.cache_control = "private, max-age=0"
    blob.upload_from_string(blob_bytes, content_type="text/plain")
    return {ENV_OBJECT: len(blob_bytes), "keys": len(selected)}


def fetch_runtime() -> dict[str, str]:
    client = _client()
    blob = client.bucket(BUCKET).blob(ENV_OBJECT)
    if not blob.exists():
        return {}
    return parse_env_bytes(blob.download_as_bytes())


def apply_runtime_secrets() -> None:
    """Fill missing env from the private object. Never overrides existing values."""
    global _loaded
    if _loaded:
        return
    if (os.environ.get("ASR_SKIP_ENV_FILE") or "").strip().lower() in ("1", "true", "yes", "on"):
        return
    if (os.environ.get("ASR_SKIP_GCS_SECRETS") or "").strip().lower() in ("1", "true", "yes", "on"):
        return
    if (os.environ.get("K_SERVICE") or "").strip() or (os.environ.get("CLOUD_RUN_JOB") or "").strip():
        return
    _loaded = True
    try:
        parsed = fetch_runtime()
    except Exception:
        return
    for key, val in parsed.items():
        if val and not denied(key):
            os.environ.setdefault(key, val)
