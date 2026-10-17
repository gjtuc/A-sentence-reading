"""design/411 — reading spots of one account, shared live by its devices."""

from __future__ import annotations

from collections.abc import Callable

from fastapi import APIRouter, Body, Request, Response
from fastapi.responses import JSONResponse

from sentence_reading.llm import reading_spots

router = APIRouter(tags=["spots"])

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


@router.get("/api/spots")
def spots_since(request: Request, since: int = 0):
    uid, denied = _gate(request)
    if denied is not None:
        return denied
    rev, spots = reading_spots.since(uid, max(0, since))
    return {"ok": True, "rev": rev, "spots": spots}


@router.put("/api/spots/{cache_id}")
def spots_put(cache_id: str, request: Request, body: dict = Body(default_factory=dict)):
    uid, denied = _gate(request)
    if denied is not None:
        return denied
    if not reading_spots.valid_cache_id(cache_id):
        return _fail(400, "bad_cache_id")
    spot = reading_spots.clean_spot(body)
    if spot is None:
        return _fail(400, "bad_spot")
    status, rev = reading_spots.put(uid, cache_id, spot)
    if status == "store_failed":
        return _fail(503, "spot_store_failed")
    return {"ok": True, "rev": rev, "applied": status == "ok"}
