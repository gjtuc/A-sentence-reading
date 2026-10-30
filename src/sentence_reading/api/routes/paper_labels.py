"""design/490 - the title and kind a reader gave a paper, shared by one account's devices."""

from __future__ import annotations

from collections.abc import Callable

from fastapi import APIRouter, Body, Request, Response
from fastapi.responses import JSONResponse

from sentence_reading.llm import paper_labels

router = APIRouter(tags=["paper_labels"])

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


@router.get("/api/paper-labels")
def paper_labels_all(request: Request):
    uid, denied = _gate(request)
    if denied is not None:
        return denied
    rev, rows = paper_labels.labels(uid)
    return {"ok": True, "rev": rev, "labels": rows}


@router.put("/api/paper-labels/{cache_id}")
def paper_labels_put(cache_id: str, request: Request, body: dict = Body(default_factory=dict)):
    uid, denied = _gate(request)
    if denied is not None:
        return denied
    if not paper_labels.valid_cache_id(cache_id):
        return _fail(400, "bad_cache_id")
    label = paper_labels.clean_label(body)
    if label is None:
        return _fail(400, "bad_label")
    status, rev = paper_labels.put(uid, cache_id, label)
    if status == "store_failed":
        return _fail(503, "paper_labels_store_failed")
    return {"ok": True, "rev": rev, "applied": status == "ok"}
