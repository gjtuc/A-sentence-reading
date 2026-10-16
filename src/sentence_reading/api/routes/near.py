"""design/410 — near-sync signaling (phone <-> web of one account)."""

from __future__ import annotations

from collections.abc import Callable

from fastapi import APIRouter, Body, Request, Response
from fastapi.responses import JSONResponse

from sentence_reading.llm import near_links

router = APIRouter(tags=["near"])

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


@router.post("/api/near/links")
def near_create(request: Request, body: dict = Body(default_factory=dict)):
    uid, denied = _gate(request)
    if denied is not None:
        return denied
    offer = near_links.clean_description(body.get("offer"), "offer")
    if offer is None:
        return _fail(400, "bad_offer")
    link_id = near_links.create(uid, offer)
    if link_id is None:
        return _fail(503, "link_store_failed")
    return {"ok": True, "link_id": link_id, "expires_in": near_links.LINK_LIFE_S}


@router.post("/api/near/links/claim")
def near_claim(request: Request):
    uid, denied = _gate(request)
    if denied is not None:
        return denied
    status, link_id, offer = near_links.claim_newest(uid)
    if status != "ok":
        return _fail(404, "no_open_link")
    return {"ok": True, "link_id": link_id, "offer": offer}


@router.post("/api/near/links/{link_id}/answer")
def near_answer(link_id: str, request: Request, body: dict = Body(default_factory=dict)):
    uid, denied = _gate(request)
    if denied is not None:
        return denied
    if not near_links.valid_link_id(link_id):
        return _fail(400, "bad_link_id")
    answer = near_links.clean_description(body.get("answer"), "answer")
    if answer is None:
        return _fail(400, "bad_answer")
    status = near_links.put_answer(uid, link_id, answer)
    if status != "ok":
        code = {"not_found": 404, "expired": 410}.get(status, 409)
        return _fail(code, status)
    return {"ok": True}


@router.get("/api/near/links/{link_id}")
def near_peek(link_id: str, request: Request):
    uid, denied = _gate(request)
    if denied is not None:
        return denied
    if not near_links.valid_link_id(link_id):
        return _fail(400, "bad_link_id")
    status, row = near_links.peek(uid, link_id)
    if status != "ok":
        return _fail(410 if status == "expired" else 404, status)
    return {"ok": True, **row}


@router.delete("/api/near/links/{link_id}")
def near_remove(link_id: str, request: Request):
    uid, denied = _gate(request)
    if denied is not None:
        return denied
    if not near_links.valid_link_id(link_id):
        return _fail(400, "bad_link_id")
    near_links.remove(uid, link_id)
    return {"ok": True}


def _relay_args(link_id: str, side: str, seq: int) -> JSONResponse | None:
    if not near_links.valid_link_id(link_id):
        return _fail(400, "bad_link_id")
    if side not in near_links.RELAY_SIDES:
        return _fail(400, "bad_side")
    if seq < 0 or seq > 10_000_000:
        return _fail(400, "bad_seq")
    return None


@router.post("/api/near/relay/{link_id}/{side}/{seq}")
async def near_relay_put(link_id: str, side: str, seq: int, request: Request):
    uid, denied = _gate(request)
    if denied is not None:
        return denied
    bad = _relay_args(link_id, side, seq)
    if bad is not None:
        return bad
    data = await request.body()
    if not data or len(data) > near_links.RELAY_MAX_BYTES:
        return _fail(413, "bad_bundle_size")
    if not near_links.relay_put(uid, link_id, side, seq, data):
        return _fail(503, "relay_store_failed")
    return {"ok": True}


@router.get("/api/near/relay/{link_id}/{side}/{seq}")
def near_relay_take(link_id: str, side: str, seq: int, request: Request):
    uid, denied = _gate(request)
    if denied is not None:
        return denied
    bad = _relay_args(link_id, side, seq)
    if bad is not None:
        return bad
    data = near_links.relay_take(uid, link_id, side, seq)
    if data is None:
        return Response(status_code=204)
    return Response(content=data, media_type="application/octet-stream")


@router.delete("/api/near/relay/{link_id}")
def near_relay_wipe(link_id: str, request: Request):
    uid, denied = _gate(request)
    if denied is not None:
        return denied
    if not near_links.valid_link_id(link_id):
        return _fail(400, "bad_link_id")
    near_links.relay_wipe(uid, link_id)
    return {"ok": True}
