"""
무엇을: 카카오 OAuth 인가 코드 → 사용자 id.
환경: ASR_KAKAO_REST_API_KEY · (선택) ASR_KAKAO_CLIENT_SECRET
Redirect: {origin}/api/auth/kakao/callback
"""

from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from sentence_reading.llm.env import load_asr_env

log = logging.getLogger(__name__)

KAKAO_AUTH = "https://kauth.kakao.com/oauth/authorize"
KAKAO_TOKEN = "https://kauth.kakao.com/oauth/token"
KAKAO_ME = "https://kapi.kakao.com/v2/user/me"


def kakao_rest_key() -> str:
    load_asr_env()
    return (os.environ.get("ASR_KAKAO_REST_API_KEY") or "").strip()


def kakao_client_secret() -> str:
    load_asr_env()
    return (os.environ.get("ASR_KAKAO_CLIENT_SECRET") or "").strip()


def kakao_enabled() -> bool:
    return bool(kakao_rest_key())


def kakao_authorize_url(*, redirect_uri: str, state: str) -> str:
    q = urllib.parse.urlencode(
        {
            "client_id": kakao_rest_key(),
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "state": state,
        }
    )
    return f"{KAKAO_AUTH}?{q}"


def _http_form(url: str, data: dict[str, str], *, headers: dict[str, str] | None = None) -> dict[str, Any]:
    body = urllib.parse.urlencode(data).encode("utf-8")
    req = urllib.request.Request(url, data=body, method="POST")
    req.add_header("Content-Type", "application/x-www-form-urlencoded;charset=utf-8")
    if headers:
        for k, v in headers.items():
            req.add_header(k, v)
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            raw = resp.read()
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:300]
        raise ValueError(f"kakao_http_{exc.code}: {detail}") from exc
    try:
        out = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("kakao_bad_json") from exc
    if not isinstance(out, dict):
        raise ValueError("kakao_bad_payload")
    return out


def _http_get_json(url: str, *, headers: dict[str, str]) -> dict[str, Any]:
    req = urllib.request.Request(url, method="GET")
    for k, v in headers.items():
        req.add_header(k, v)
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            raw = resp.read()
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:300]
        raise ValueError(f"kakao_http_{exc.code}: {detail}") from exc
    try:
        out = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("kakao_bad_json") from exc
    if not isinstance(out, dict):
        raise ValueError("kakao_bad_payload")
    return out


def exchange_code(code: str, *, redirect_uri: str) -> dict[str, Any]:
    """인가 코드 → access_token + 카카오 프로필."""
    c = (code or "").strip()
    if not c:
        raise ValueError("empty_code")
    data = {
        "grant_type": "authorization_code",
        "client_id": kakao_rest_key(),
        "redirect_uri": redirect_uri,
        "code": c,
    }
    secret = kakao_client_secret()
    if secret:
        data["client_secret"] = secret
    token = _http_form(KAKAO_TOKEN, data)
    access = str(token.get("access_token") or "").strip()
    if not access:
        raise ValueError("no_access_token")
    me = _http_get_json(
        KAKAO_ME,
        headers={"Authorization": f"Bearer {access}"},
    )
    kid = me.get("id")
    if kid is None:
        raise ValueError("no_kakao_id")
    subject = str(kid)
    kakao_account = me.get("kakao_account") if isinstance(me.get("kakao_account"), dict) else {}
    profile = (
        kakao_account.get("profile")
        if isinstance(kakao_account.get("profile"), dict)
        else {}
    )
    email = str(kakao_account.get("email") or "")
    name = str(profile.get("nickname") or "")
    picture = str(profile.get("profile_image_url") or "")
    return {
        "subject": subject,
        "email": email,
        "name": name,
        "picture": picture,
    }
