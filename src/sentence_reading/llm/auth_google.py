"""
무엇을: Google ID 토큰 검증 + 세션 쿠키 + 요청 단위 UID (GCS 칸).
왜: 기기·클라이언트가 달라도 같은 계정 = 같은 users/{uid}/ 창고 (design/22).
환경: ASR_GOOGLE_CLIENT_ID · ASR_AUTH_SECRET(선택)
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import os
import re
import secrets
import time
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any

from sentence_reading.llm.env import load_asr_env

log = logging.getLogger(__name__)

COOKIE_NAME = "asr_session"
SESSION_MAX_AGE_SEC = 60 * 60 * 24 * 30  # 30일
_UID_RE = re.compile(r"^[A-Za-z0-9_\-]{6,128}$")

_gcs_uid: ContextVar[str | None] = ContextVar("asr_gcs_uid", default=None)


@dataclass(frozen=True)
class AuthUser:
    uid: str
    email: str = ""
    name: str = ""
    picture: str = ""

    def public_dict(self) -> dict[str, str]:
        return {
            "uid": self.uid,
            "email": self.email,
            "name": self.name,
            "picture": self.picture,
        }


def auth_client_id() -> str:
    load_asr_env()
    return (os.environ.get("ASR_GOOGLE_CLIENT_ID") or "").strip()


def email_auth_enabled() -> bool:
    """이메일 가입/로그인. ASR_EMAIL_AUTH=0 이면 끔 (기본 on)."""
    load_asr_env()
    v = (os.environ.get("ASR_EMAIL_AUTH") or "1").strip().lower()
    return v not in ("0", "false", "no", "off")


def auth_enabled() -> bool:
    """Google·카카오·이메일 중 하나라도 켜져 있으면 로그인 UI·UID 칸 모드."""
    from sentence_reading.llm.auth_kakao import kakao_enabled

    return bool(auth_client_id()) or kakao_enabled() or email_auth_enabled()


def auth_secret() -> str:
    load_asr_env()
    secret = (os.environ.get("ASR_AUTH_SECRET") or "").strip()
    if secret:
        return secret
    # WHY: 로컬 개발 기본값 — 프로덕션에서는 ASR_AUTH_SECRET 필수 권장
    return "asr-dev-auth-secret-change-me"


def cookie_secure() -> bool:
    """
    HTTPS 전용 세션 쿠키 (Cloud Run).
    ASR_COOKIE_SECURE=1|true 이면 Secure.
    """
    load_asr_env()
    v = (os.environ.get("ASR_COOKIE_SECURE") or "").strip().lower()
    return v in ("1", "true", "yes", "on")


def sanitize_uid(raw: str | None) -> str | None:
    uid = (raw or "").strip()
    if not _UID_RE.match(uid):
        return None
    return uid


def current_gcs_uid() -> str | None:
    return _gcs_uid.get()


def set_gcs_uid(uid: str | None) -> None:
    safe = sanitize_uid(uid) if uid else None
    _gcs_uid.set(safe)


def reset_gcs_uid() -> None:
    _gcs_uid.set(None)


def _b64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _b64url_decode(text: str) -> bytes | None:
    s = (text or "").strip()
    if not s:
        return None
    pad = "=" * (-len(s) % 4)
    try:
        return base64.urlsafe_b64decode(s + pad)
    except (ValueError, TypeError):
        return None


def _sign(payload_b64: str) -> str:
    dig = hmac.new(
        auth_secret().encode("utf-8"),
        payload_b64.encode("ascii"),
        hashlib.sha256,
    ).digest()
    return _b64url_encode(dig)


def issue_session_token(user: AuthUser) -> str:
    """HMAC 서명 세션 (stdlib only — itsdangerous 불필요)."""
    body = {
        "uid": user.uid,
        "email": user.email,
        "name": user.name,
        "picture": user.picture,
        "iat": int(time.time()),
    }
    payload_b64 = _b64url_encode(
        json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    )
    return f"{payload_b64}.{_sign(payload_b64)}"


def parse_session_token(token: str | None) -> AuthUser | None:
    if not token or not isinstance(token, str) or "." not in token:
        return None
    payload_b64, _, sig = token.partition(".")
    if not payload_b64 or not sig:
        return None
    expected = _sign(payload_b64)
    if not hmac.compare_digest(expected, sig):
        return None
    raw = _b64url_decode(payload_b64)
    if not raw:
        return None
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    try:
        iat = int(data.get("iat") or 0)
    except (TypeError, ValueError):
        return None
    if iat <= 0 or (time.time() - iat) > SESSION_MAX_AGE_SEC:
        return None
    uid = sanitize_uid(str(data.get("uid") or ""))
    if not uid:
        return None
    return AuthUser(
        uid=uid,
        email=str(data.get("email") or "")[:320],
        name=str(data.get("name") or "")[:200],
        picture=str(data.get("picture") or "")[:500],
    )


def verify_google_id_token(credential: str) -> AuthUser:
    """
    GIS credential (JWT) 검증 → AuthUser.
    여기서 uid 필드는 Google subject (창고 UID는 auth_accounts.resolve 가 결정).
    """
    client_id = auth_client_id()
    if not client_id:
        raise ValueError("ASR_GOOGLE_CLIENT_ID missing")
    token = (credential or "").strip()
    if not token or len(token) > 16_000:
        raise ValueError("invalid credential")

    from google.auth.transport import requests as google_requests
    from google.oauth2 import id_token

    info = id_token.verify_oauth2_token(
        token,
        google_requests.Request(),
        client_id,
        clock_skew_in_seconds=60,
    )
    if not isinstance(info, dict):
        raise ValueError("invalid token payload")
    iss = str(info.get("iss") or "")
    if iss not in ("accounts.google.com", "https://accounts.google.com"):
        raise ValueError("invalid issuer")
    uid = sanitize_uid(str(info.get("sub") or ""))
    if not uid:
        raise ValueError("invalid subject")
    return AuthUser(
        uid=uid,
        email=str(info.get("email") or "")[:320],
        name=str(info.get("name") or "")[:200],
        picture=str(info.get("picture") or "")[:500],
    )


def issue_oauth_state(mode: str, *, link_uid: str | None = None) -> str:
    """카카오 redirect state (mode=login|link)."""
    m = (mode or "login").strip().lower()
    if m not in ("login", "link"):
        m = "login"
    body = {
        "m": m,
        "u": (link_uid or "")[:128],
        "iat": int(time.time()),
        "n": secrets.token_hex(8),
    }
    payload_b64 = _b64url_encode(
        json.dumps(body, separators=(",", ":")).encode("utf-8")
    )
    return f"{payload_b64}.{_sign(payload_b64)}"


def parse_oauth_state(state: str | None) -> dict[str, str] | None:
    if not state or "." not in state:
        return None
    payload_b64, _, sig = state.partition(".")
    if not payload_b64 or not sig or not hmac.compare_digest(_sign(payload_b64), sig):
        return None
    raw = _b64url_decode(payload_b64)
    if not raw:
        return None
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    try:
        iat = int(data.get("iat") or 0)
    except (TypeError, ValueError):
        return None
    if iat <= 0 or (time.time() - iat) > 600:
        return None
    mode = str(data.get("m") or "login")
    if mode not in ("login", "link"):
        return None
    return {"mode": mode, "link_uid": str(data.get("u") or "")}


def auth_status_fields(user: AuthUser | None = None) -> dict[str, Any]:
    from sentence_reading.llm.auth_accounts import public_user_with_providers
    from sentence_reading.llm.auth_kakao import kakao_enabled

    load_asr_env()
    enabled = auth_enabled()
    google_on = bool(auth_client_id())
    kakao_on = kakao_enabled()
    email_on = email_auth_enabled()
    user_out: dict[str, Any] | None = None
    if user:
        user_out = public_user_with_providers(user)
    cloud_url = (os.environ.get("ASR_CLOUD_RUN_URL") or "").strip().rstrip("/")
    return {
        "auth_enabled": enabled,
        "auth_provider": "multi" if enabled else None,
        "providers": {
            "google": google_on,
            "kakao": kakao_on,
            "email": email_on,
        },
        "client_id": auth_client_id() if google_on else None,
        "cloud_url": cloud_url or None,
        "user": user_out,
        "gcs_uid": current_gcs_uid(),
        "gcs_user_scoped": bool(current_gcs_uid()),
    }


def new_csrf_nonce() -> str:
    return secrets.token_urlsafe(16)
