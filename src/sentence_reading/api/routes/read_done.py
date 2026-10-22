"""design/442 — papers marked as read to the end, shared by the devices of one account."""

from __future__ import annotations

from collections.abc import Callable

from fastapi import APIRouter, Body, Request, Response
from fastapi.responses import JSONResponse

from sentence_reading.llm import reading_done

router = APIRouter(tags=["read_done"])

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


@router.get("/api/read-done")
def read_done_all(request: Request):
    uid, denied = _gate(request)
    if denied is not None:
        return denied
    rev, marks = reading_done.marks(uid)
    return {"ok": True, "rev": rev, "marks": marks}


@router.put("/api/read-done/{cache_id}")
def read_done_put(cache_id: str, request: Request, body: dict = Body(default_factory=dict)):
    uid, denied = _gate(request)
    if denied is not None:
        return denied
    if not reading_done.valid_cache_id(cache_id):
        return _fail(400, "bad_cache_id")
    mark = reading_done.clean_mark(body)
    if mark is None:
        return _fail(400, "bad_mark")
    status, rev = reading_done.put(uid, cache_id, mark)
    if status == "store_failed":
        return _fail(503, "read_done_store_failed")
    return {"ok": True, "rev": rev, "applied": status == "ok"}
