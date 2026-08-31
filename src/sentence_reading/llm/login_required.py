# -*- coding: utf-8 -*-
"""design/83 — global login-required gate (identity), separate from access OTP (67).

INVARIANT: when enabled + auth configured, anonymous callers only reach
login-needed surfaces. Paid invite gate (67) still applies after login.
"""
from __future__ import annotations

import os

from sentence_reading.llm.env import load_asr_env

# Exact API paths that must stay reachable without a session so login works.
_PUBLIC_API_EXACT = frozenset(
    {
        "/api/status",
        "/api/auth/status",
        "/api/auth/google",
        "/api/auth/google/mobile/start",
        "/api/auth/kakao/start",
        "/api/auth/kakao/callback",
        "/api/auth/email/login",
        "/api/auth/email/register",
        "/api/auth/email/magic/request",
        "/api/auth/email/magic/open",
        "/api/auth/logout",
        "/api/mobile/apk",
    }
)

_PUBLIC_PAGE_EXACT = frozenset({"/", "/favicon.ico"})


def login_required_enabled() -> bool:
    """design/83 kill — ASR_LOGIN_REQUIRED=0 off (default on)."""
    load_asr_env()
    v = (os.environ.get("ASR_LOGIN_REQUIRED") or "1").strip().lower()
    return v not in ("0", "false", "off", "no")


def is_login_public_path(path: str) -> bool:
    """Return True if anonymous access is allowed for this path.

    WHY narrow allowlist: product locks everything else behind login.
    EDGE: trailing slash normalized; /static/* and login HTML stay open.
    """
    raw = (path or "").strip() or "/"
    # EDGE: collapse accidental double slashes from proxies.
    while "//" in raw:
        raw = raw.replace("//", "/")
    if len(raw) > 1 and raw.endswith("/"):
        raw = raw.rstrip("/")
    if raw in _PUBLIC_API_EXACT or raw in _PUBLIC_PAGE_EXACT:
        return True
    if raw.startswith("/static/"):
        return True
    return False
