"""design/255 Phase 2 — request auth and paid-access helpers.

Handlers still live in app.py; routers import these names so TTS/status
binds and route modules share one implementation.
"""

from __future__ import annotations

from fastapi import Request
from fastapi.responses import JSONResponse

from sentence_reading.llm.access_gate import (
    access_gate_enabled,
    public_access_view,
    user_may_use_paid,
)
from sentence_reading.llm.auth_google import AuthUser, auth_enabled


def request_user(request: Request) -> AuthUser | None:
    user = getattr(request.state, "auth_user", None)
    return user if isinstance(user, AuthUser) else None


def is_admin_user(user: AuthUser | None) -> bool:
    if user is None:
        return False
    from sentence_reading.llm.usage_meter import is_admin_email

    return is_admin_email(user.email)


def paid_access_denied(request: Request) -> JSONResponse | None:
    """Return 403/401 if access gate blocks paid APIs; else None."""
    if not access_gate_enabled():
        return None
    user = request_user(request)
    if user is None:
        if auth_enabled():
            return JSONResponse(
                status_code=401,
                content={
                    "ok": False,
                    "error": "auth_required",
                    "message": "로그인 후 이용해 주세요.",
                },
            )
        return None
    if user_may_use_paid(
        user.uid, email=user.email or "", is_admin=is_admin_user(user)
    ):
        return None
    view = public_access_view(
        user.uid, email=user.email or "", is_admin=is_admin_user(user)
    )
    return JSONResponse(
        status_code=403,
        content={
            "ok": False,
            "error": "access_denied",
            "access": view,
            "message": "초대 코드 승인 후 이용할 수 있습니다. (관리자 Allow 필요)",
        },
    )
