"""design/457 - the library list of each device of one account (import list marks)."""

from __future__ import annotations

from collections.abc import Callable

from fastapi import APIRouter, Body, Request, Response
from fastapi.responses import JSONResponse

from sentence_reading.llm import library_keys

router = APIRouter(tags=["library_keys"])

_PaidDenied = Callable[[Request], Response | None]
_paid_access_denied: _PaidDenied | None = None


def bind(*, paid_access_denied: _PaidDenied) -> None:
    """Wire app.py auth helper once at startup (avoids circular imports)."""
    global _paid_access_denied
    _paid_access_denied = paid_access_denied


def _fail(status: int, error: str) -> JSONResponse:
    return JSONResponse(status_code=status, content={"ok": False, "error": error})


def _gate(request: Request) -> tuple[str | None, Response | None]:
    if _paid_access_denied is not None:
        denied = _paid_access_denied(request)
        if denied is not None:
            return None, denied
    user = getattr(request.state, "auth_user", None)
    uid = getattr(user, "uid", None)
    if not uid:
        return None, _fail(401, "auth_required")
    return str(uid), None


@router.get("/api/library-keys")
def library_keys_all(request: Request):
    uid, denied = _gate(request)
    if denied is not None:
        return denied
    rev, devices = library_keys.lists(uid)
    return {"ok": True, "rev": rev, "devices": devices}


@router.put("/api/library-keys")
def library_keys_put(request: Request, body: dict = Body(default_factory=dict)):
    uid, denied = _gate(request)
    if denied is not None:
        return denied
    cleaned = library_keys.clean_list(body)
    if cleaned is None:
        return _fail(400, "bad_list")
    dev, at, items = cleaned
    status, rev = library_keys.put(uid, dev, at, items)
    if status == "store_failed":
        return _fail(503, "library_keys_store_failed")
    return {"ok": True, "rev": rev, "applied": status == "ok"}
